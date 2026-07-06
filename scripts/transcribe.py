"""WebVTT parsing and transcript formatting."""

from __future__ import annotations

import html
import re
from pathlib import Path

TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\s+-->\s+"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)"
)
TAG_RE = re.compile(r"<[^>]+>")


def parse_timestamp(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"invalid VTT timestamp: {value!r}")


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def clean_caption_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"<\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?>", "", text)
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_vtt(path_or_text: str | Path) -> list[dict[str, object]]:
    if isinstance(path_or_text, Path) or Path(str(path_or_text)).exists():
        text = Path(path_or_text).read_text(encoding="utf-8", errors="replace")
    else:
        text = str(path_or_text)

    entries: list[dict[str, object]] = []
    current_timing: tuple[float, float] | None = None
    current_lines: list[str] = []
    skip_block = False

    def flush() -> None:
        nonlocal current_timing, current_lines
        if current_timing is None:
            current_lines = []
            return
        caption = clean_caption_text(current_lines)
        if caption:
            entries.append({"start": current_timing[0], "end": current_timing[1], "text": caption})
        current_timing = None
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip("\ufeff").strip()
        if not line:
            flush()
            skip_block = False
            continue
        if line == "WEBVTT" or line.startswith(("Kind:", "Language:")):
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            skip_block = True
            continue
        if skip_block:
            continue

        match = TIMING_RE.search(line)
        if match:
            flush()
            current_timing = (
                parse_timestamp(match.group("start")),
                parse_timestamp(match.group("end")),
            )
            continue
        if current_timing is not None:
            current_lines.append(line)

    flush()
    return dedupe_segments(entries)


def dedupe_segments(segments: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    for segment in segments:
        text = str(segment["text"]).strip()
        start = float(segment["start"])
        end = float(segment["end"])
        if not text:
            continue
        previous = deduped[-1] if deduped else None
        if previous and previous["text"] == text and float(previous["end"]) >= start - 0.25:
            previous["end"] = max(float(previous["end"]), end)
            continue
        deduped.append({"start": start, "end": end, "text": text})
    return deduped


def filter_range(
    segments: list[dict[str, object]], start: float | None, end: float | None
) -> list[dict[str, object]]:
    filtered = []
    start_s = 0.0 if start is None else float(start)
    end_s = float("inf") if end is None else float(end)
    for segment in segments:
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        if seg_end < start_s or seg_start > end_s:
            continue
        filtered.append(segment)
    return filtered


def format_transcript(segments: list[dict[str, object]]) -> str:
    lines = []
    for segment in segments:
        lines.append(f"[{format_timestamp(float(segment['start']))}] {segment['text']}")
    return "\n".join(lines)
