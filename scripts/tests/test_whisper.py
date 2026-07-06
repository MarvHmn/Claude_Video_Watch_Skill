import urllib.error
from email.message import Message

import pytest
import whisper


def test_parse_env_file_handles_quotes_comments_and_whitespace(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# comment
GROQ_API_KEY = "abc"
OPENAI_API_KEY='def'
EMPTY=
""",
        encoding="utf-8",
    )

    values = whisper.parse_env_file(env_file)

    assert values["GROQ_API_KEY"] == "abc"
    assert values["OPENAI_API_KEY"] == "def"
    assert values["EMPTY"] == ""


def test_multipart_form_data_contains_fields_and_file(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")

    body, content_type = whisper.multipart_form_data({"model": "whisper-1"}, {"file": audio})

    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="model"' in body
    assert b"whisper-1" in body
    assert b'filename="audio.mp3"' in body
    assert b"audio" in body


def test_request_retries_429_then_succeeds(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            headers = Message()
            headers["Retry-After"] = "0"
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limit",
                headers,
                None,
            )
        return Response()

    monkeypatch.setattr(whisper.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(whisper.time, "sleep", lambda delay: None)

    provider = whisper.Provider("openai", whisper.OPENAI_ENDPOINT, "secret", "whisper-1")

    assert whisper._request(provider, b"body", "multipart/form-data") == b"ok"
    assert len(calls) == 2


def test_request_does_not_retry_non_429_client_error(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, None)

    monkeypatch.setattr(whisper.urllib.request, "urlopen", fake_urlopen)
    provider = whisper.Provider("groq", whisper.GROQ_ENDPOINT, "secret", "whisper-large-v3")

    with pytest.raises(whisper.WhisperError):
        whisper._request(provider, b"body", "multipart/form-data")
    assert len(calls) == 1


def test_provider_endpoint_guard():
    provider = whisper.Provider("groq", whisper.OPENAI_ENDPOINT, "secret", "whisper-large-v3")

    with pytest.raises(whisper.WhisperError):
        whisper._assert_provider_endpoint(provider)
