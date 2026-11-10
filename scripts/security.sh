#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
scanner_dir="$PWD/.local/tools"
mkdir -p "$scanner_dir"
if [[ ! -x "$scanner_dir/gitleaks" ]]; then
  curl --fail --silent --show-error --location --retry 3 https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz --output "$scanner_dir/gitleaks.tar.gz"
  echo "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb  $scanner_dir/gitleaks.tar.gz" | sha256sum --check
  tar -xzf "$scanner_dir/gitleaks.tar.gz" -C "$scanner_dir" gitleaks
fi
python3 scripts/repository_data_guard.py --base "${BASE_SHA:-}"
"$scanner_dir/gitleaks" git . --log-opts='--all --full-history' --redact=100 --max-decode-depth=3 --max-archive-depth=3
