#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
UV_PROJECT_ENVIRONMENT="$PWD/.venv-triposr" uv sync --project backends/triposr --locked --python 3.11
.venv-triposr/bin/python -m unittest discover -s backends/triposr -p 'test_*.py'
.venv-triposr/bin/python backends/triposr/check.py --write-marker
