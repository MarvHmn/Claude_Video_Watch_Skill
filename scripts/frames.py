"""Frame extraction and video metadata helpers."""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class VideoMetadata:
    duration: float
    width: int | None
    height: int | None
    fps: float | None


@dataclass(frozen=True)
class Frame:
    path: Path
    timestamp: float
    kind: str = "frame"


class FrameExtractionError(RuntimeError):
    """Raised when ffmpeg or ffprobe cannot process the video."""


def parse_time(value: str | float | int | None) -> float | None:
    """Parse seconds, MM:SS, or HH:MM:SS into seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("time cannot be negative")
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    if text.startswith("-"):
        raise ValueError("time cannot be negative")

    parts = text.split(":")
    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            minutes, sec = parts
            seconds = int(minutes) * 60 + float(sec)
        elif len(parts) == 3:
            hours, minutes, sec = parts
            seconds = int(hours) * 3600 + int(minutes) * 60 + float(sec)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"invalid time value: {value!r}") from exc

    if seconds < 0:
        raise ValueError("time cannot be negative")
    return seconds


def format_time(seconds: float | int | None) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    if seconds is None or not math.isfinite(float(seconds)):
        return "00:00"
    total = max(0, int(round(float(seconds))))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def timestamp_slug(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    return f"{millis:010d}ms"


def parse_fps(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def get_metadata(video_path: str | Path) -> VideoMetadata:
    path = Path(video_path).expanduser().resolve()
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise FrameExtractionError(result.stderr.strip() or "ffprobe failed")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FrameExtractionError("ffprobe returned invalid JSON") from exc

    streams = payload.get("streams") or []
    stream = streams[0] if streams else {}
    duration_raw = (payload.get("format") or {}).get("duration") or 0
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = 0.0

    return VideoMetadata(
        duration=max(0.0, duration),
        width=_int_or_none(stream.get("width")),
        height=_int_or_none(stream.get("height")),
        fps=parse_fps(stream.get("avg_frame_rate")) or parse_fps(stream.get("r_frame_rate")),
    )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def frame_budget(duration: float, max_frames: int = 80, focused: bool = False) -> int:
    """Return the target frame budget for a duration."""
    if duration <= 0:
        return 1
    hard_cap = min(max_frames, 100)
    if focused:
        return max(1, min(hard_cap, math.ceil(duration * 2)))
    if duration <= 30:
        target = math.ceil(duration)
    elif duration <= 60:
        target = 40
    elif duration <= 180:
        target = 60
    elif duration <= 600:
        target = 80
    else:
        target = 100
    return max(1, min(hard_cap, target))


def auto_fps(duration: float, max_frames: int = 80, focused: bool = False) -> float:
    """Pick an fps that honors the frame budget and the 2fps hard cap."""
    if duration <= 0:
        return 1.0
    budget = frame_budget(duration, max_frames=max_frames, focused=focused)
    return max(0.01, min(2.0, budget / duration))


def extract(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    resolution: int = 512,
    fps: float | None = None,
    max_frames: int = 80,
    start: float | None = None,
    end: float | None = None,
    scene_change: bool = True,
) -> list[Frame]:
    """Extract representative frames from a video."""
    video = Path(video_path).expanduser().resolve()
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = get_metadata(video)
    start_s = parse_time(start) or 0.0
    end_s = parse_time(end)
    if end_s is not None and end_s <= start_s:
        raise ValueError("--end must be greater than --start")

    available_duration = max(0.0, metadata.duration - start_s)
    window_duration = min(available_duration, end_s - start_s) if end_s else available_duration
    focused = start_s > 0 or end_s is not None
    target_fps = fps if fps is not None else auto_fps(window_duration, max_frames, focused=focused)
    target_fps = min(2.0, max(0.01, target_fps))
    target_count = frame_budget(window_duration, max_frames=max_frames, focused=focused)

    if scene_change:
        frames = extract_scene_change(
            video,
            output_dir,
            resolution=resolution,
            max_frames=target_count,
            start=start_s,
            end=end_s,
        )
        if 3 <= len(frames) <= max(3, target_count * 2):
            return _cap_frames(frames, target_count)

    return extract_uniform(
        video,
        output_dir,
        resolution=resolution,
        fps=target_fps,
        max_frames=target_count,
        start=start_s,
        end=end_s,
    )


def extract_scene_change(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    resolution: int = 512,
    max_frames: int = 80,
    start: float = 0.0,
    end: float | None = None,
) -> list[Frame]:
    """Extract scene-change frames using ffmpeg's scene score filter."""
    video = Path(video_path).expanduser().resolve()
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    best: list[Frame] = []
    for threshold in (0.42, 0.32, 0.24, 0.16):
        candidate_dir = output_dir / f"scene_{str(threshold).replace('.', '_')}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        pattern = str(candidate_dir / "scene_%05d.jpg")
        vf = f"select='gt(scene,{threshold})',showinfo,scale={int(resolution)}:-2"
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *(_time_input_args(start, end)),
            "-i",
            str(video),
            "-vf",
            vf,
            "-vsync",
            "vfr",
            "-q:v",
            "2",
            pattern,
        ]
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        files = sorted(candidate_dir.glob("scene_*.jpg"))
        if result.returncode != 0 and not files:
            continue

        times = _parse_showinfo_times(result.stderr, offset=start)
        frames = _frames_from_files(files, times, kind="scene")
        if not best or _score_scene_count(len(frames), max_frames) < _score_scene_count(
            len(best), max_frames
        ):
            best = frames
        if 3 <= len(frames) <= max_frames:
            break

    return _rename_frames(best, output_dir, prefix="scene")


def extract_uniform(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    resolution: int = 512,
    fps: float = 1.0,
    max_frames: int = 80,
    start: float = 0.0,
    end: float | None = None,
) -> list[Frame]:
    """Extract uniformly spaced frames."""
    video = Path(video_path).expanduser().resolve()
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = output_dir / "uniform_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(raw_dir / "frame_%05d.jpg")
    fps = min(2.0, max(0.01, fps))
    vf = f"fps={fps:.6f},scale={int(resolution)}:-2"

    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *(_time_input_args(start, end)),
        "-i",
        str(video),
        "-vf",
        vf,
        "-q:v",
        "2",
        pattern,
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    files = sorted(raw_dir.glob("frame_*.jpg"))
    if result.returncode != 0 and not files:
        raise FrameExtractionError(result.stderr.strip() or "ffmpeg frame extraction failed")

    selected = _select_evenly(files, max_frames)
    frames = [
        Frame(path=path, timestamp=start + (index / fps), kind="uniform")
        for index, path in enumerate(selected)
    ]
    return _rename_frames(frames, output_dir, prefix="frame")


def select_hero_frames(frames: Iterable[Frame], count: int = 6) -> list[Frame]:
    return _cap_frames(list(frames), max(1, count))


def _time_input_args(start: float | None, end: float | None) -> list[str]:
    args: list[str] = []
    if start and start > 0:
        args.extend(["-ss", f"{start:.3f}"])
    if end is not None and start is not None:
        duration = max(0.001, end - start)
        args.extend(["-t", f"{duration:.3f}"])
    return args


def _parse_showinfo_times(stderr: str, *, offset: float) -> list[float]:
    times: list[float] = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", stderr):
        try:
            times.append(offset + float(match.group(1)))
        except ValueError:
            continue
    return times


def _frames_from_files(files: list[Path], times: list[float], *, kind: str) -> list[Frame]:
    if not files:
        return []
    if len(times) < len(files):
        times = [float(i) for i in range(len(files))]
    return [Frame(path=file, timestamp=times[i], kind=kind) for i, file in enumerate(files)]


def _score_scene_count(count: int, target: int) -> int:
    if count < 3:
        return 10_000 + (3 - count)
    return abs(target - count)


def _select_evenly(items: list[Path], max_count: int) -> list[Path]:
    if len(items) <= max_count:
        return items
    if max_count <= 1:
        return [items[0]]
    selected = []
    last_index = len(items) - 1
    for slot in range(max_count):
        index = round(slot * last_index / (max_count - 1))
        selected.append(items[index])
    return selected


def _cap_frames(frames: list[Frame], max_count: int) -> list[Frame]:
    if len(frames) <= max_count:
        return frames
    if max_count <= 1:
        return [frames[0]]
    selected = []
    last_index = len(frames) - 1
    for slot in range(max_count):
        index = round(slot * last_index / (max_count - 1))
        selected.append(frames[index])
    return selected


def _rename_frames(frames: list[Frame], output_dir: Path, *, prefix: str) -> list[Frame]:
    renamed: list[Frame] = []
    for index, frame in enumerate(frames, start=1):
        target = output_dir / f"{prefix}_{index:03d}_{timestamp_slug(frame.timestamp)}.jpg"
        if frame.path.resolve() != target.resolve():
            frame.path.replace(target)
        renamed.append(Frame(path=target.resolve(), timestamp=frame.timestamp, kind=frame.kind))
    return renamed
