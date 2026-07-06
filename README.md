# Claude Video Watch Skill

An in-house Claude Code `/watch` skill for analyzing video from a URL or local
file. It downloads or opens the video, extracts representative frames,
transcribes captions or audio, computes basic editorial pacing metrics, and
emits a structured report for Claude to complete.

This implementation is a clean stdlib-only rebuild from the internal
implementation plan. It does not vendor third-party skill code.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe`
- `yt-dlp` for URL sources
- Optional Whisper fallback key:
  - `GROQ_API_KEY` for Groq `whisper-large-v3`
  - `OPENAI_API_KEY` for OpenAI `whisper-1`

The Python runtime has no pip dependencies.

## Install

### Claude Code Plugin

Install this repository as a Claude Code plugin:

```text
/plugin install https://github.com/MarvHmn/Claude_Video_Watch_Skill
```

The plugin includes the `/watch` slash command, the skill definition, and a
session-start setup hook.

### claude.ai Skill Bundle

Download `watch.skill` from a tagged release and upload it to claude.ai.
Maintainers can build the bundle locally:

```sh
scripts/build-skill.sh
```

### Bare Skill Folder

Copy this folder into `~/.claude/skills/watch`.

## Usage

```text
/watch https://example.com/video "What are the key claims?"
/watch ~/Downloads/demo.mp4 "Summarize the hook and pacing"
```

Focused analysis can use `--start` and `--end` through the underlying runtime:

```sh
python3 scripts/watch.py ~/Downloads/demo.mp4 --start 01:10 --end 01:45 --intent "What changes in this section?"
```

Best results are under 10 minutes. Longer videos are processed sparsely with a
hard cap of 100 frames.

## What Leaves The Machine

- URL mode runs `yt-dlp` against the user-supplied URL.
- If captions are absent and Whisper is enabled, the extracted mono MP3 audio is
  uploaded to Groq or OpenAI. The runtime prints a one-line disclosure before
  upload.
- `--no-whisper` disables all audio upload.

API endpoints are fixed constants in `scripts/whisper.py`. Groq keys are only
sent to `api.groq.com`; OpenAI keys are only sent to `api.openai.com`.

## Key Storage

Keys can be supplied by environment variable or by `~/.config/watch/.env`:

```dotenv
GROQ_API_KEY=
OPENAI_API_KEY=
SETUP_COMPLETE=true
```

The setup script creates this file with `0600` permissions and never writes real
key values automatically. Runtime output and generated reports never include API
keys.

## Security Notes

Video transcripts and visible on-screen text are untrusted data. The skill tells
Claude not to follow instructions that appear inside video content.

Subprocess calls are argv-only; the code does not use `shell=True`. Inputs are
resolved to absolute paths before being passed to `ffmpeg` or `ffprobe`, and
`yt-dlp` receives `--` before the URL to prevent option injection.

Vault ingest is opt-in. The skill never autodetects home-directory vaults, never
opens `obsidian://` URLs, and never writes to a vault unless `WATCH_VAULT_DIR`
or `VAULT_DIR` is configured and the user consents.

Residual risk remains in `yt-dlp` and `ffmpeg` parsing arbitrary remote media.
Keep both updated.

## Development

Run tests:

```sh
python3 -m pytest
```

Run formatting and lint checks:

```sh
ruff format --check .
ruff check .
```

## Project Layout

```text
SKILL.md
commands/watch.md
hooks/
scripts/
.github/workflows/
```
