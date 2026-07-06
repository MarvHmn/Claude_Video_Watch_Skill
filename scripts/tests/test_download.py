from pathlib import Path

import download
import pytest


def test_is_url_accepts_http_https_with_netloc():
    assert download.is_url("https://example.com/watch?v=1")
    assert download.is_url("http://example.com/video.mp4")


@pytest.mark.parametrize(
    "source",
    [
        "-o output",
        "file:///tmp/video.mp4",
        "https:///missing-host",
        "example.com/video",
        "",
    ],
)
def test_is_url_rejects_unsafe_or_non_url_values(source):
    assert not download.is_url(source)


def test_local_file_rejects_dash_prefixed_path():
    with pytest.raises(download.AcquisitionError):
        download.local_file("-video.mp4")


def test_local_file_returns_resolved_path(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not real video")

    acquired = download.local_file(str(video))

    assert acquired.video_path == video.resolve()
    assert acquired.subtitle_path is None
    assert acquired.downloaded is False
    assert acquired.info["title"] == "clip"


def test_find_downloaded_video_ignores_sidecars(tmp_path):
    (tmp_path / "video.info.json").write_text("{}", encoding="utf-8")
    (tmp_path / "video.en.vtt").write_text("WEBVTT", encoding="utf-8")
    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"video")

    assert download._find_downloaded_video(Path(tmp_path)) == mp4
