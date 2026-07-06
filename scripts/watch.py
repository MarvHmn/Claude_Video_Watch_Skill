#!/usr/bin/env python3
"""Orchestrate video acquisition, frame extraction, transcription, and reporting."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import download
import frames
import hook
import pacing
import report
import transcribe
import whisper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch a video and produce an analysis manifest")
    parser.add_argument("source", help="Video URL or local file path")
    parser.add_argument("--intent", default="", help="Question or analysis intent")
    parser.add_argument("--max-frames", type=int, default=80, help="Maximum frames to emit")
    parser.add_argument("--resolution", type=int, default=512, help="Frame width in pixels")
    parser.add_argument("--fps", type=float, default=None, help="Override uniform extraction fps")
    parser.add_argument("--start", default=None, help="Focused start time")
    parser.add_argument("--end", default=None, help="Focused end time")
    parser.add_argument("--out-dir", default=None, help="Output/work directory")
    parser.add_argument(
        "--whisper", choices=["groq", "openai"], default=None, help="Preferred backend"
    )
    parser.add_argument("--no-whisper", action="store_true", help="Do not upload audio for Whisper")
    parser.add_argument(
        "--no-scene-change", action="store_true", help="Use uniform frame extraction"
    )
    parser.add_argument(
        "--no-hook-microscope",
        action="store_true",
        help="Skip 0-10s dense hook extraction and word-level transcript",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Retained for transparency; workdirs are not recursively deleted",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    start = frames.parse_time(args.start)
    end = frames.parse_time(args.end)
    if end is not None and start is not None and end <= start:
        parser.error("--end must be greater than --start")

    workdir = Path(args.out_dir).expanduser().resolve() if args.out_dir else _temp_workdir()
    workdir.mkdir(parents=True, exist_ok=True)
    frame_dir = workdir / "frames"
    frame_dir.mkdir(exist_ok=True)

    acquisition = download.acquire(args.source, workdir)
    metadata = frames.get_metadata(acquisition.video_path)
    duration = metadata.duration
    if duration > 600 and not (start or end):
        print("warning: video is over 10 minutes; using sparse frame extraction", file=sys.stderr)

    frame_list = frames.extract(
        acquisition.video_path,
        frame_dir,
        resolution=args.resolution,
        fps=args.fps,
        max_frames=args.max_frames,
        start=start,
        end=end,
        scene_change=not args.no_scene_change,
    )

    transcript = _load_transcript(
        acquisition=acquisition,
        workdir=workdir,
        no_whisper=args.no_whisper,
        whisper_backend=args.whisper,
        start=start,
        end=end,
    )

    scene_timestamps = [frame.timestamp for frame in frame_list if frame.kind == "scene"]
    window_duration = _window_duration(duration, start, end)
    pacing_data = pacing.pacing_metrics(scene_timestamps, duration=window_duration)
    pacing_data["motion_scores"] = pacing.motion_scores_from_frames(frame_list)

    hook_data = None
    if not args.no_hook_microscope:
        hook_data = hook.analyze_hook(
            acquisition.video_path,
            workdir,
            resolution=args.resolution,
            whisper_backend=args.whisper,
            use_whisper=not args.no_whisper,
        )

    title = str(acquisition.info.get("title") or Path(acquisition.video_path).stem)
    report_path = report.emit_report(
        workdir / "report.md",
        title=title,
        source_url=str(acquisition.info.get("url") or args.source),
        duration=duration,
        intent=args.intent,
        frames=frame_list,
        transcript=transcript,
        pacing=pacing_data,
        hook=hook_data,
    )

    print_manifest(
        source=args.source,
        acquisition=acquisition,
        metadata=metadata,
        intent=args.intent,
        frames_list=frame_list,
        transcript=transcript,
        pacing_data=pacing_data,
        hook_data=hook_data,
        report_path=report_path,
        workdir=workdir,
        whisper_disabled=args.no_whisper,
    )
    return 0


def _temp_workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="watch-")).resolve()


def _window_duration(duration: float, start: float | None, end: float | None) -> float:
    start_s = start or 0.0
    end_s = end if end is not None else duration
    return max(0.0, min(duration, end_s) - start_s)


def _load_transcript(
    *,
    acquisition: download.Acquisition,
    workdir: Path,
    no_whisper: bool,
    whisper_backend: str | None,
    start: float | None,
    end: float | None,
) -> str:
    if acquisition.subtitle_path:
        segments = transcribe.parse_vtt(acquisition.subtitle_path)
        segments = transcribe.filter_range(segments, start, end)
        return transcribe.format_transcript(segments)
    if no_whisper:
        return ""
    try:
        vtt = whisper.transcribe_video(
            acquisition.video_path,
            workdir,
            preferred=whisper_backend,
            start=start,
            end=end,
        )
    except whisper.WhisperError as exc:
        print(f"warning: Whisper unavailable: {exc}", file=sys.stderr)
        return ""
    segments = transcribe.parse_vtt(vtt)
    return transcribe.format_transcript(segments) if segments else vtt.strip()


def print_manifest(
    *,
    source: str,
    acquisition: download.Acquisition,
    metadata: frames.VideoMetadata,
    intent: str,
    frames_list: list[frames.Frame],
    transcript: str,
    pacing_data: dict[str, object],
    hook_data: dict[str, object] | None,
    report_path: Path,
    workdir: Path,
    whisper_disabled: bool,
) -> None:
    print("# Watch Manifest")
    print()
    print(f"- Source: {source}")
    print(f"- Video file: {acquisition.video_path}")
    print(f"- Downloaded: {str(acquisition.downloaded).lower()}")
    print(f"- Duration: {frames.format_time(metadata.duration)}")
    print(f"- Dimensions: {metadata.width or '?'}x{metadata.height or '?'}")
    print(f"- FPS: {metadata.fps or '?'}")
    print(f"- Intent: {intent or '(none)'}")
    print(f"- Report: {report_path}")
    print(f"- Workdir: {workdir}")
    print(f"- Whisper disabled: {str(whisper_disabled).lower()}")
    print()
    print("## Frames")
    print()
    for frame in frames_list:
        print(f"- [{frames.format_time(frame.timestamp)}] {frame.path}")
    print()
    print("## Pacing")
    print()
    print("```json")
    print(json.dumps(pacing_data, indent=2))
    print("```")
    if hook_data:
        print()
        print("## Hook Microscope")
        print()
        print("```json")
        print(json.dumps(hook_data, indent=2))
        print("```")
    print()
    print("## Transcript")
    print()
    print(transcript.strip() or "(no transcript available)")


if __name__ == "__main__":
    raise SystemExit(main())
