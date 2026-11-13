#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential libpq-dev git

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip wheel
pip install -e .

echo "Python environment installed. Copy .env.example to .env and configure it."
