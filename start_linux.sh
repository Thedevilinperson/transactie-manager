#!/usr/bin/env bash
# Transactie Manager - starten op Linux of macOS.
set -e
WORTEL="$(cd "$(dirname "$0")" && pwd)"
cd "$WORTEL/transactie_manager"

if [ ! -d "$WORTEL/.venv" ]; then
  echo "Virtuele omgeving aanmaken..."
  python3 -m venv "$WORTEL/.venv"
  . "$WORTEL/.venv/bin/activate"
  pip install --upgrade pip
  pip install -r requirements.txt
else
  . "$WORTEL/.venv/bin/activate"
fi

export TM_DATA_DIR="$WORTEL/data"
exec python start.py --geen-browser
