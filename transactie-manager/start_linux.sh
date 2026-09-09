#!/usr/bin/env bash
# Transactie Manager - starten op Linux of macOS.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Virtuele omgeving aanmaken..."
  python3 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  . .venv/bin/activate
fi

export TM_DATA_DIR="$(pwd)/data"
exec python start.py --geen-browser
