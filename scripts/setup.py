"""Preflight and installer for the watch skill."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "watch" / ".env"
REQUIRED_BINARIES = ("ffmpeg", "ffprobe", "yt-dlp")


def parse_env_file(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return values
    for raw_line in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_status() -> dict[str, object]:
    missing = [binary for binary in REQUIRED_BINARIES if shutil.which(binary) is None]
    env_values = parse_env_file(CONFIG_FILE)
    has_key = bool(
        os.environ.get("GROQ_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or env_values.get("GROQ_API_KEY")
        or env_values.get("OPENAI_API_KEY")
    )
    setup_complete = env_values.get("SETUP_COMPLETE") == "true"
    permissions = _permissions(CONFIG_FILE)
    permission_warning = CONFIG_FILE.exists() and permissions not in {"600", "400"}
    return {
        "ready": not missing and has_key,
        "missing_binaries": missing,
        "has_key": has_key,
        "setup_complete": setup_complete,
        "config_file": str(CONFIG_FILE),
        "permissions": permissions,
        "permission_warning": permission_warning,
    }


def exit_code_for_status(status: dict[str, object]) -> int:
    missing_binaries = bool(status["missing_binaries"])
    missing_key = not bool(status["has_key"])
    if missing_binaries and missing_key:
        return 4
    if missing_binaries:
        return 2
    if missing_key:
        return 3
    return 0


def scaffold_config() -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
        return
    CONFIG_FILE.write_text(
        "\n".join(
            [
                "# Claude Video Watch Skill configuration",
                "# Fill one of these manually if you want Whisper transcription.",
                "GROQ_API_KEY=",
                "OPENAI_API_KEY=",
                "# Optional explicit vault destination.",
                "VAULT_DIR=",
                "SETUP_COMPLETE=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)


def install() -> int:
    scaffold_config()
    missing = [binary for binary in REQUIRED_BINARIES if shutil.which(binary) is None]
    if not missing:
        print("watch setup: binaries present; config scaffolded")
        return 0

    system = platform.system()
    if system == "Darwin":
        if shutil.which("brew") is None:
            print("Homebrew is not installed. Install ffmpeg and yt-dlp, then rerun setup.")
            return 2
        packages = []
        if "ffmpeg" in missing or "ffprobe" in missing:
            packages.append("ffmpeg")
        if "yt-dlp" in missing:
            packages.append("yt-dlp")
        result = subprocess.run(["brew", "install", *packages], check=False)
        return result.returncode

    if system == "Linux":
        print("Install ffmpeg and yt-dlp with your system package manager, then rerun setup.")
        print("Examples: apt-get install ffmpeg; python -m pip install --upgrade yt-dlp")
        return 2

    if system == "Windows":
        print("Install ffmpeg from ffmpeg.org and yt-dlp with: py -m pip install --upgrade yt-dlp")
        return 2

    print("Install ffmpeg and yt-dlp for this operating system, then rerun setup.")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Setup checker and installer for watch skill")
    parser.add_argument("--check", action="store_true", help="Check dependencies and exit")
    parser.add_argument("--json", action="store_true", help="Print JSON status")
    args = parser.parse_args(argv)

    if args.check:
        status = check_status()
        if args.json:
            print(json.dumps(status, indent=2))
        elif status["permission_warning"]:
            print(
                f"warning: {CONFIG_FILE} should be readable only by the current user",
                file=sys.stderr,
            )
        return exit_code_for_status(status)

    code = install()
    status = check_status()
    if args.json:
        print(json.dumps(status, indent=2))
    elif status["permission_warning"]:
        print(
            f"warning: {CONFIG_FILE} should be readable only by the current user",
            file=sys.stderr,
        )
    return code


def _permissions(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)[2:]


if __name__ == "__main__":
    raise SystemExit(main())
