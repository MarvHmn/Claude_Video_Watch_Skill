import transcribe


def test_parse_vtt_dedupes_overlapping_segments():
    text = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
Hello <b>world</b>

2
00:00:01.900 --> 00:00:03.000
Hello world

3
00:00:04.000 --> 00:00:05.000
Next line
"""

    segments = transcribe.parse_vtt(text)

    assert segments == [
        {"start": 0.0, "end": 3.0, "text": "Hello world"},
        {"start": 4.0, "end": 5.0, "text": "Next line"},
    ]


def test_filter_range_keeps_overlapping_segments():
    segments = [
        {"start": 1.0, "end": 2.0, "text": "before"},
        {"start": 3.0, "end": 4.0, "text": "inside"},
        {"start": 9.0, "end": 10.0, "text": "after"},
    ]

    filtered = transcribe.filter_range(segments, 2.5, 8.0)

    assert filtered == [{"start": 3.0, "end": 4.0, "text": "inside"}]


def test_format_transcript():
    assert (
        transcribe.format_transcript([{"start": 62.0, "end": 63.0, "text": "Hello"}])
        == "[01:02] Hello"
    )
