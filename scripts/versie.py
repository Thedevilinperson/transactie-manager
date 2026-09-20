#!/usr/bin/env python3
"""Zet één versienummer op alle plaatsen waar het staat.

Gebruik:
    python scripts/versie.py 0.7.2

Het nummer staat op zes plaatsen, waaronder een merkteken bovenaan het
stijlblad. Dat laatste laat de toepassing zien wanneer een browser nog een oude
opmaak gebruikt. Dat handmatig bijhouden gaat vroeg of laat mis, vandaar dit
script.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent

PLAATSEN = [
    ("VERSION", r"^.*$", "{versie}"),
    ("transactie_manager/app/config.py", r'^VERSION = ".*"$', 'VERSION = "{versie}"'),
    ("transactie_manager/config.yaml", r'^version: ".*"$', 'version: "{versie}"'),
    ("transactie_manager/app/static/css/stijl.css",
     r'^  --stijl-versie: ".*";$', '  --stijl-versie: "{versie}";'),
    ("README.md", r"^\*\*Versie .*\*\*", "**Versie {versie}**"),
    ("transactie_manager/docs/HANDLEIDING.md", r"^Versie .*$", "Versie {versie}"),
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    versie = sys.argv[1].strip()

    for pad, patroon, vervanging in PLAATSEN:
        bestand = WORTEL / pad
        tekst = bestand.read_text(encoding="utf-8")
        nieuw, aantal = re.subn(patroon, vervanging.format(versie=versie), tekst,
                                count=1, flags=re.MULTILINE)
        if aantal == 0:
            print(f"  LET OP: niets gevonden om te vervangen in {pad}")
            continue
        bestand.write_text(nieuw, encoding="utf-8")
        print(f"  {pad}")

    print(f"\nVersie staat op {versie}. Vul nu het wijzigingslogboek aan in "
          "transactie_manager/CHANGELOG.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
