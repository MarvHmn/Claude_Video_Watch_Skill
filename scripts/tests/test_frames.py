import math

import frames
import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12", 12),
        ("01:02", 62),
        ("01:02:03", 3723),
        ("00:00:01.500", 1.5),
    ],
)
def test_parse_time(raw, expected):
    assert frames.parse_time(raw) == expected


def test_parse_time_rejects_negative():
    with pytest.raises(ValueError):
        frames.parse_time("-1")


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (10, 10),
        (30, 30),
        (45, 40),
        (120, 60),
        (400, 80),
        (1200, 80),
    ],
)
def test_frame_budget_default_max(duration, expected):
    assert frames.frame_budget(duration, max_frames=80) == expected


def test_frame_budget_hard_cap_and_focus():
    assert frames.frame_budget(1200, max_frames=200) == 100
    assert frames.frame_budget(20, max_frames=80, focused=True) == 40
    assert frames.frame_budget(80, max_frames=80, focused=True) == 80


def test_auto_fps_never_exceeds_two():
    assert frames.auto_fps(5, max_frames=80) <= 2
    assert math.isclose(frames.auto_fps(20, max_frames=80, focused=True), 2.0)


def test_format_time():
    assert frames.format_time(62) == "01:02"
    assert frames.format_time(3723) == "01:02:03"
