from pathlib import Path

import whisper

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def read_script(name):
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_no_subprocess_shell_true_in_runtime():
    for path in SCRIPTS.glob("*.py"):
        assert "shell=True" not in path.read_text(encoding="utf-8"), path


def test_no_requests_or_http_imports_outside_whisper():
    for path in SCRIPTS.glob("*.py"):
        if path.name == "whisper.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "import requests" not in text
        assert "from requests" not in text
        assert "import http" not in text
        assert "from http" not in text


def test_whisper_endpoints_are_fixed_constants():
    assert whisper.GROQ_ENDPOINT == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert whisper.OPENAI_ENDPOINT == "https://api.openai.com/v1/audio/transcriptions"


def test_setup_installer_does_not_use_privileged_command_text():
    assert "sudo" not in read_script("setup.py")


def test_download_yt_dlp_uses_url_terminator():
    text = read_script("download.py")
    assert '"--",' in text
    assert "url," in text
