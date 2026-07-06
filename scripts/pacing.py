"""Editorial pacing metrics."""

from __future__ import annotations

import statistics
from pathlib import Path

from frames import Frame


def pacing_metrics(scene_timestamps: list[float], *, duration: float) -> dict[str, object]:
    timestamps = sorted(t for t in scene_timestamps if t >= 0)
    if duration <= 0:
        duration = timestamps[-1] if timestamps else 0.0
    cuts = max(0, len(timestamps))
    cuts_per_min = cuts / (duration / 60) if duration > 0 else 0.0

    boundaries = [0.0, *timestamps]
    if duration and (not boundaries or boundaries[-1] < duration):
        boundaries.append(duration)
    shot_lengths = [
        round(boundaries[i + 1] - boundaries[i], 3)
        for i in range(len(boundaries) - 1)
        if boundaries[i + 1] > boundaries[i]
    ]

    return {
        "duration": round(duration, 3),
        "cuts": cuts,
        "cuts_per_min": round(cuts_per_min, 2),
        "mean_shot_length": round(statistics.mean(shot_lengths), 3) if shot_lengths else None,
        "median_shot_length": round(statistics.median(shot_lengths), 3) if shot_lengths else None,
        "shot_lengths": shot_lengths,
    }


def motion_scores_from_frames(frames: list[Frame]) -> list[dict[str, object]]:
    """Cheap motion proxy based on adjacent JPEG byte-size deltas."""
    scores: list[dict[str, object]] = []
    previous_size: int | None = None
    for frame in frames:
        size = _file_size(frame.path)
        if previous_size is None:
            previous_size = size
            continue
        denominator = max(previous_size, size, 1)
        delta = abs(size - previous_size) / denominator
        scores.append({"timestamp": frame.timestamp, "score": round(delta, 4)})
        previous_size = size
    return scores


def _file_size(path: str | Path) -> int:
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0
