#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# The CPU check environment is always separate from the owner's CUDA environment.
UV_PROJECT_ENVIRONMENT=.venv-check uv sync --locked --extra cpu --extra dev
.venv-check/bin/python -m playwright install chromium
npm ci
npm run build
