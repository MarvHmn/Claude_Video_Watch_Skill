#!/usr/bin/env sh
set -eu

missing=""

if ! command -v ffmpeg >/dev/null 2>&1; then
  missing="${missing} ffmpeg"
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  missing="${missing} yt-dlp"
fi

config_file="${WATCH_CONFIG_FILE:-$HOME/.config/watch/.env}"
has_key="false"
setup_complete="false"
perm_warning=""

if [ -f "$config_file" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      GROQ_API_KEY=*)
        value=${line#GROQ_API_KEY=}
        [ -n "$value" ] && has_key="true"
        ;;
      OPENAI_API_KEY=*)
        value=${line#OPENAI_API_KEY=}
        [ -n "$value" ] && has_key="true"
        ;;
      SETUP_COMPLETE=true)
        setup_complete="true"
        ;;
    esac
  done < "$config_file"

  perms=$(stat -f "%Lp" "$config_file" 2>/dev/null || stat -c "%a" "$config_file" 2>/dev/null || printf "")
  if [ -n "$perms" ] && [ "$perms" != "600" ] && [ "$perms" != "400" ]; then
    perm_warning=" config permissions should be 600 or 400"
  fi
fi

if [ -n "${GROQ_API_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ]; then
  has_key="true"
fi

if [ -n "$missing" ] || [ "$has_key" != "true" ] || [ "$setup_complete" != "true" ] || [ -n "$perm_warning" ]; then
  printf "watch setup incomplete:%s%s%s%s\n" \
    "$missing" \
    "$( [ "$has_key" = "true" ] || printf " whisper-key" )" \
    "$( [ "$setup_complete" = "true" ] || printf " setup-marker" )" \
    "$perm_warning"
fi
