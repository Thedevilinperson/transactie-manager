#!/usr/bin/env python3
"""Zet de map klaar die je naar /addons/transactie_manager/ kopieert.

Gebruik:
    python scripts/bouw_addon.py [doelmap]

Zonder doelmap wordt ./build/transactie_manager gebruikt.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
ADDON = WORTEL / "homeassistant-addon"

BESTANDEN = ["requirements.txt", "wsgi.py", "start.py"]
MAPPEN = ["app"]
ADDON_BESTANDEN = ["config.yaml", "Dockerfile", "run.sh", "README.md"]


def main() -> int:
    doel = Path(sys.argv[1]) if len(sys.argv) > 1 else WORTEL / "build" / "transactie_manager"
    if doel.exists():
        shutil.rmtree(doel)
    doel.mkdir(parents=True)

    for naam in ADDON_BESTANDEN:
        shutil.copy2(ADDON / naam, doel / naam)
    for naam in BESTANDEN:
        shutil.copy2(WORTEL / naam, doel / naam)
    for naam in MAPPEN:
        shutil.copytree(
            WORTEL / naam, doel / naam,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    print(f"Klaar. Kopieer {doel} naar /addons/transactie_manager/ op je "
          "Home Assistant-systeem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
