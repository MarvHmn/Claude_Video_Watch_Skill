#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

git diff --quiet
git diff --cached --quiet

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p dist

git archive --format=tar --prefix=watch/ HEAD | tar -xf - -C "$tmp_dir"

rm -rf \
  "$tmp_dir/watch/.claude-plugin" \
  "$tmp_dir/watch/.github" \
  "$tmp_dir/watch/commands" \
  "$tmp_dir/watch/hooks"

file_count=$(find "$tmp_dir/watch" -type f | wc -l | tr -d ' ')
skill_count=$(find "$tmp_dir/watch" -name SKILL.md -type f | wc -l | tr -d ' ')

if [ "$file_count" -gt 200 ]; then
  printf "Refusing to build: bundle contains %s files\n" "$file_count" >&2
  exit 1
fi

if [ "$skill_count" != "1" ]; then
  printf "Refusing to build: bundle must contain exactly one SKILL.md\n" >&2
  exit 1
fi

python3 - "$tmp_dir/watch" "$repo_root/dist/watch.skill" <<'PY'
from pathlib import Path
import sys
import zipfile

src = Path(sys.argv[1])
dest = Path(sys.argv[2])

with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(src.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(src.parent))
PY

printf "Built dist/watch.skill\n"
