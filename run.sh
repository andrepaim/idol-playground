#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -x .venv/bin/uvicorn ]]; then
  idol_server=.venv/bin/uvicorn
elif [[ -x .venv-check/bin/uvicorn ]]; then
  idol_server=.venv-check/bin/uvicorn
else
  printf '%s\n' 'Run make bootstrap first. For splats, also run make setup-local models.' >&2
  exit 1
fi
if [[ ! -f dist/index.html ]]; then
  printf '%s\n' 'Run npm ci and npm run build first.' >&2
  exit 1
fi
exec "$idol_server" app:app --host 127.0.0.1 --port "${PORT:-8000}"
