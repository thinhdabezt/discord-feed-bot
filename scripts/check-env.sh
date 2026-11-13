#!/usr/bin/env bash
set -euo pipefail
python3 --version
python3 -c "import platform; print('Architecture:', platform.machine())"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python -c "import discord, httpx, sqlalchemy; print('Core imports: OK')"
else
  echo "Virtual environment not found."
  exit 1
fi
