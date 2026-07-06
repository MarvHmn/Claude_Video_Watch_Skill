import report
from frames import Frame


def test_slugify_strips_traversal_unicode_and_limits_length():
    assert report.slugify("../../Über Video!!") == "uber-video"
    assert report.slugify("x" * 100) == "x" * 60
    assert report.slugify("///", fallback="Fallback Title") == "fallback-title"


def test_emit_report_contains_all_pending_markers(tmp_path):
    frame_file = tmp_path / "frame.jpg"
    frame_file.write_bytes(b"jpg")
    frame = Frame(path=frame_file, timestamp=1.0)

    path = report.emit_report(
        tmp_path / "report.md",
        title="Demo",
        source_url="https://example.com",
        duration=12.3,
        intent="Summarize",
        frames=[frame],
        transcript="[00:01] hello",
        pacing={"cuts": 1},
        hook={"window": "00:00-00:10"},
    )

    text = path.read_text(encoding="utf-8")
    for marker in (
        "tldr",
        "key moments",
        "hook breakdown",
        "editorial profile",
        "quotable moments",
        "entities",
        "concepts",
    ):
        assert f"pending Claude fill: {marker}" in text
    assert "hero_frames:" in text
    assert "[00:01] hello" in text


def test_save_to_vault_copies_only_when_called(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report", encoding="utf-8")
    frame_path = tmp_path / "hero.jpg"
    frame_path.write_bytes(b"jpg")

    target = report.save_to_vault(
        vault_dir=vault,
        report_path=report_path,
        hero_frames=[Frame(path=frame_path, timestamp=0.0)],
        title="My Demo",
        source_url="https://example.com",
    )

    assert target == vault / "watched" / "my-demo"
    assert (target / "report.md").exists()
    assert (target / "frames" / "hero.jpg").exists()
    assert "My Demo" in (vault / "watch-log.md").read_text(encoding="utf-8")
