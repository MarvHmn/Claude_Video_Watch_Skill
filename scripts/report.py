"""Structured report generation and optional vault helpers."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import unicodedata
from pathlib import Path

from frames import Frame, format_time, select_hero_frames

PENDING_SECTIONS = [
    ("TL;DR", "tldr"),
    ("Key Moments", "key moments"),
    ("Hook Breakdown", "hook breakdown"),
    ("Editorial Profile", "editorial profile"),
    ("Quotable Moments", "quotable moments"),
    ("Entities", "entities"),
    ("Concepts", "concepts"),
]


def slugify(value: str, *, fallback: str | None = None, max_length: int = 60) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)[:max_length].strip("-")
    if slug:
        return slug
    if fallback:
        return slugify(fallback, max_length=max_length)
    return f"video-{dt.date.today().isoformat()}"


def emit_report(
    report_path: str | Path,
    *,
    title: str,
    source_url: str,
    duration: float,
    intent: str,
    frames: list[Frame],
    transcript: str,
    pacing: dict[str, object],
    hook: dict[str, object] | None = None,
) -> Path:
    path = Path(report_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    heroes = select_hero_frames(frames, count=6)
    frontmatter = {
        "title": title,
        "source_url": source_url,
        "duration": round(duration, 3),
        "intent": intent,
        "hero_frames": [str(frame.path) for frame in heroes],
        "date": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }

    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=True)}")
    lines.extend(["---", "", f"# {title}", ""])

    for heading, marker in PENDING_SECTIONS:
        lines.extend([f"## {heading}", "", f"<!-- pending Claude fill: {marker} -->", ""])

    lines.extend(["## Pacing Metrics", "", "```json", json.dumps(pacing, indent=2), "```", ""])

    if hook:
        lines.extend(
            ["## Hook Microscope Data", "", "```json", json.dumps(hook, indent=2), "```", ""]
        )

    lines.extend(["## Frames", ""])
    for frame in frames:
        lines.append(f"- [{format_time(frame.timestamp)}] {frame.path}")
    lines.append("")

    lines.extend(["## Full Transcript", ""])
    if transcript.strip():
        lines.append(transcript.strip())
    else:
        lines.append("<!-- pending Claude fill: full transcript unavailable -->")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def save_to_vault(
    *,
    vault_dir: str | Path,
    report_path: str | Path,
    hero_frames: list[Frame],
    title: str,
    source_url: str,
) -> Path:
    """Copy report and hero frames into an explicitly configured vault directory."""
    vault = Path(vault_dir).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        raise ValueError(f"vault directory does not exist: {vault}")

    slug = slugify(title)
    target = vault / "watched" / slug
    target.mkdir(parents=True, exist_ok=False)

    copied_report = target / "report.md"
    shutil.copy2(Path(report_path).resolve(), copied_report)
    frames_dir = target / "frames"
    frames_dir.mkdir()
    for frame in hero_frames:
        shutil.copy2(frame.path, frames_dir / frame.path.name)

    with (vault / "watch-log.md").open("a", encoding="utf-8") as handle:
        handle.write(
            f"- {dt.date.today().isoformat()} [{title}](watched/{slug}/report.md) {source_url}\n"
        )

    return target
