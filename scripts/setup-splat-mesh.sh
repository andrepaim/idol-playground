#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
UV_PROJECT_ENVIRONMENT="$PWD/.venv-stereo" uv sync --project experiments/splat_mesh --locked --python 3.11
.venv-stereo/bin/python -m playwright install chromium
.venv-stereo/bin/python backends/splat_mesh/check.py --write-marker
