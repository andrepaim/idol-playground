#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
UV_PROJECT_ENVIRONMENT="$PWD/.venv-unirig" uv sync --project backends/unirig --locked --python 3.11
.venv-unirig/bin/python backends/unirig/check.py --write-marker
