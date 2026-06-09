#!/usr/bin/env bash
# pre-commit hook entrypoint: run the frontend's own ESLint on staged files.
# pre-commit passes repo-relative paths (frontend/src/...); ESLint runs from
# frontend/ so the flat config resolves, hence the prefix strip.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -eq 0 ]]; then
  exit 0
fi

files=()
for f in "$@"; do
  files+=("${f#frontend/}")
done

cd frontend
exec pnpm exec eslint --max-warnings 0 "${files[@]}"
