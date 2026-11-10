#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/uvicorn || ! -f dist/index.html ]]; then
  printf '%s\n' 'Run uv sync --extra local, npm ci, and npm run build first.' >&2
  exit 1
fi
exec .venv/bin/uvicorn app:app --host 127.0.0.1 --port "${PORT:-8000}"
