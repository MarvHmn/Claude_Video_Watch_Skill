"""0-10 second hook microscope."""

from __future__ import annotations

from pathlib import Path

import frames
import whisper


def analyze_hook(
    video_path: str | Path,
    out_dir: str | Path,
    *,
    resolution: int = 512,
    whisper_backend: str | None = None,
    use_whisper: bool = True,
) -> dict[str, object]:
    hook_dir = Path(out_dir).expanduser().resolve() / "hook"
    hook_dir.mkdir(parents=True, exist_ok=True)

    hook_frames = frames.extract_uniform(
        video_path,
        hook_dir,
        resolution=resolution,
        fps=2.0,
        max_frames=20,
        start=0.0,
        end=10.0,
    )
    words = ""
    if use_whisper:
        try:
            words = whisper.transcribe_video(
                video_path,
                hook_dir,
                preferred=whisper_backend,
                start=0.0,
                end=10.0,
                word_timestamps=True,
            )
        except whisper.WhisperError as exc:
            words = f"Whisper unavailable: {exc}"

    return {
        "window": "00:00-00:10",
        "frames": [str(frame.path) for frame in hook_frames],
        "word_timestamps": words,
    }
