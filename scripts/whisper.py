"""Groq/OpenAI Whisper clients with fixed endpoints and no SDK dependency."""

from __future__ import annotations

import json
import mimetypes
import os
import random
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
OPENAI_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
GROQ_HOST = "api.groq.com"
OPENAI_HOST = "api.openai.com"
USER_AGENT = "ClaudeVideoWatchSkill/1.0"


@dataclass(frozen=True)
class Provider:
    name: str
    endpoint: str
    key: str
    model: str


class WhisperError(RuntimeError):
    """Raised when Whisper transcription fails."""


def parse_env_file(path: str | Path) -> dict[str, str]:
    env: dict[str, str] = {}
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return env
    for raw_line in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env[key] = value
    return env


def load_key_values(config_file: str | Path | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    values.update(parse_env_file(Path.cwd() / ".env"))
    default_config = Path.home() / ".config" / "watch" / ".env"
    values.update(parse_env_file(config_file or default_config))
    for key in ("GROQ_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def available_providers(preferred: str | None = None) -> list[Provider]:
    keys = load_key_values()
    providers: list[Provider] = []
    if keys.get("GROQ_API_KEY"):
        providers.append(Provider("groq", GROQ_ENDPOINT, keys["GROQ_API_KEY"], "whisper-large-v3"))
    if keys.get("OPENAI_API_KEY"):
        providers.append(Provider("openai", OPENAI_ENDPOINT, keys["OPENAI_API_KEY"], "whisper-1"))
    if preferred:
        providers.sort(key=lambda provider: provider.name != preferred)
    else:
        providers.sort(key=lambda provider: provider.name != "groq")
    return providers


def extract_audio(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    start: float | None = None,
    end: float | None = None,
) -> Path:
    video = Path(video_path).expanduser().resolve()
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audio = output_dir / "audio_16k_mono.mp3"
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *(_time_args(start, end)),
        "-i",
        str(video),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        "64k",
        str(audio),
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not audio.exists():
        raise WhisperError(result.stderr.strip() or "audio extraction failed")
    return audio.resolve()


def transcribe_video(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    preferred: str | None = None,
    start: float | None = None,
    end: float | None = None,
    word_timestamps: bool = False,
) -> str:
    providers = available_providers(preferred)
    if not providers:
        raise WhisperError("missing GROQ_API_KEY or OPENAI_API_KEY")

    audio = extract_audio(video_path, out_dir, start=start, end=end)
    last_error: Exception | None = None
    for provider in providers:
        size_mb = audio.stat().st_size / (1024 * 1024)
        print(f"watch: uploading {size_mb:.1f} MB audio to {provider.name}", file=sys.stderr)
        try:
            return transcribe_audio(audio, provider, word_timestamps=word_timestamps)
        except WhisperError as exc:
            last_error = exc
            continue
    raise WhisperError(str(last_error) if last_error else "Whisper transcription failed")


def transcribe_audio(
    audio_path: str | Path, provider: Provider, *, word_timestamps: bool = False
) -> str:
    fields = {
        "model": provider.model,
        "response_format": "verbose_json" if word_timestamps else "vtt",
    }
    if word_timestamps:
        fields["timestamp_granularities[]"] = "word"
    body, content_type = multipart_form_data(fields, {"file": Path(audio_path).resolve()})
    data = _request(provider, body, content_type)
    if word_timestamps:
        return _format_words_json(data.decode("utf-8", errors="replace"))
    return data.decode("utf-8", errors="replace")


def multipart_form_data(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = "----watch-" + "".join(random.choice(string.ascii_letters) for _ in range(24))
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )

    for name, path in files.items():
        filename = path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                path.read_bytes(),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request(provider: Provider, body: bytes, content_type: str) -> bytes:
    _assert_provider_endpoint(provider)
    request = urllib.request.Request(
        provider.endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {provider.key}",
            "Content-Type": content_type,
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    attempts = 0
    rate_limit_retries = 0
    while attempts < 4:
        attempts += 1
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            if 400 <= status < 500 and status != 429:
                raise WhisperError(
                    f"{provider.name} Whisper request failed with HTTP {status}"
                ) from exc
            if status == 429:
                rate_limit_retries += 1
                if rate_limit_retries > 2:
                    raise WhisperError(f"{provider.name} Whisper rate limit persisted") from exc
                _sleep_before_retry(exc, attempts)
                continue
            if attempts >= 4:
                raise WhisperError(
                    f"{provider.name} Whisper request failed with HTTP {status}"
                ) from exc
            _sleep_before_retry(exc, attempts)
        except urllib.error.URLError as exc:
            if attempts >= 4:
                raise WhisperError(f"{provider.name} Whisper network error") from exc
            _sleep_before_retry(None, attempts)
    raise WhisperError(f"{provider.name} Whisper request failed")


def _assert_provider_endpoint(provider: Provider) -> None:
    if provider.name == "groq" and not provider.endpoint.startswith(f"https://{GROQ_HOST}/"):
        raise WhisperError("invalid Groq endpoint")
    if provider.name == "openai" and not provider.endpoint.startswith(f"https://{OPENAI_HOST}/"):
        raise WhisperError("invalid OpenAI endpoint")


def _sleep_before_retry(error: urllib.error.HTTPError | None, attempts: int) -> None:
    retry_after = error.headers.get("Retry-After") if error else None
    try:
        delay = float(retry_after) if retry_after else min(2**attempts, 8)
    except ValueError:
        delay = min(2**attempts, 8)
    time.sleep(delay)


def _time_args(start: float | None, end: float | None) -> list[str]:
    args: list[str] = []
    if start is not None and start > 0:
        args.extend(["-ss", f"{start:.3f}"])
    if start is not None and end is not None:
        args.extend(["-t", f"{max(0.001, end - start):.3f}"])
    return args


def _format_words_json(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    words = payload.get("words")
    if not isinstance(words, list):
        return text
    lines = []
    for word in words:
        if not isinstance(word, dict):
            continue
        start = word.get("start")
        token = word.get("word")
        if start is None or token is None:
            continue
        lines.append(f"[{float(start):.2f}] {token}")
    return "\n".join(lines)
