"""Video acquisition from URLs or local files."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

YTDLP_FORMAT = "bv*[height<=720]+ba/b[height<=720]/bv+ba/b"
SUB_LANGS = "en,en-US,en-GB,en-orig"
KNOWN_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".mkv",
    ".webm",
    ".avi",
    ".wmv",
    ".flv",
}


@dataclass(frozen=True)
class Acquisition:
    video_path: Path
    subtitle_path: Path | None
    info: dict[str, object]
    downloaded: bool


class AcquisitionError(RuntimeError):
    """Raised when a source cannot be acquired."""


def is_url(source: str) -> bool:
    text = source.strip()
    if not text or text.startswith("-"):
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def acquire(source: str, workdir: str | Path) -> Acquisition:
    if is_url(source):
        return download_url(source, workdir)
    return local_file(source)


def download_url(url: str, workdir: str | Path) -> Acquisition:
    if not is_url(url):
        raise AcquisitionError("source is not a valid http(s) URL")

    out_dir = Path(workdir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    argv = [
        "yt-dlp",
        "-N",
        "8",
        "-f",
        YTDLP_FORMAT,
        "--merge-output-format",
        "mp4",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        SUB_LANGS,
        "--sub-format",
        "vtt",
        "--convert-subs",
        "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o",
        str(out_dir / "video.%(ext)s"),
        "--",
        url,
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)

    video_path = _find_downloaded_video(out_dir)
    if result.returncode != 0 and video_path is None:
        tail = "\n".join((result.stderr or result.stdout).splitlines()[-8:])
        raise AcquisitionError(tail or "yt-dlp failed")
    if video_path is None:
        raise AcquisitionError("yt-dlp finished but no video file was produced")

    return Acquisition(
        video_path=video_path.resolve(),
        subtitle_path=_find_subtitle(out_dir),
        info=_load_info(out_dir, fallback_url=url),
        downloaded=True,
    )


def local_file(source: str) -> Acquisition:
    if source.strip().startswith("-"):
        raise AcquisitionError("local path cannot start with '-'")

    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise AcquisitionError(f"local file does not exist: {path}")
    if not path.is_file():
        raise AcquisitionError(f"local source is not a file: {path}")
    if path.suffix.lower() not in KNOWN_VIDEO_EXTENSIONS:
        print(f"warning: unknown video extension {path.suffix!r}", file=sys.stderr)

    return Acquisition(
        video_path=path,
        subtitle_path=None,
        info={"title": path.stem, "url": str(path), "duration": None, "uploader": None},
        downloaded=False,
    )


def _find_downloaded_video(workdir: Path) -> Path | None:
    candidates = []
    for path in workdir.glob("video.*"):
        if path.suffix.lower() in {".json", ".vtt", ".srt", ".part", ".ytdl"}:
            continue
        if path.is_file():
            candidates.append(path)
    return sorted(candidates)[0] if candidates else None


def _find_subtitle(workdir: Path) -> Path | None:
    candidates = sorted(workdir.glob("video*.vtt"))
    return candidates[0].resolve() if candidates else None


def _load_info(workdir: Path, *, fallback_url: str) -> dict[str, object]:
    candidates = sorted(workdir.glob("video*.info.json"))
    if candidates:
        try:
            with candidates[0].open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        payload = {}

    return {
        "title": payload.get("title") or "video",
        "uploader": payload.get("uploader") or payload.get("channel"),
        "duration": payload.get("duration"),
        "url": payload.get("webpage_url") or fallback_url,
    }
