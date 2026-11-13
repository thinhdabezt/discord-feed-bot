#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -d .venv ]]; then
  echo "Missing .venv. Run scripts/install-debian.sh first."
  exit 1
fi
exec .venv/bin/python -m app.main
