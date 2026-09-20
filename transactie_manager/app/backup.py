"""Kopieën van de databank, om een ingreep ongedaan te kunnen maken.

Een aantal handelingen raakt in één klik je hele boekhouding: een
referentielijst integraal vervangen, een historiek inlezen, alle regels opnieuw
toepassen. Gaat daar iets mis, dan is er zonder kopie geen weg terug — de
gegevens staan versleuteld en zijn niet met de hand te repareren.

Daarom wordt er vóór zo'n ingreep automatisch een kopie gelegd. Dat gebeurt met
`VACUUM INTO`, waarmee SQLite een sluitende kopie schrijft zonder dat de
toepassing stil hoeft te liggen; het WAL-bestand zit erin verwerkt.

De kopie is even versleuteld als het origineel: de sleutel zit niet in de
databank maar wordt uit je wachtwoord afgeleid. Een kopie terugzetten van vóór
een wachtwoordwijziging werkt dus niet — vandaar de waarschuwing op het scherm.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, DB_PATH

BACKUP_DIR = DATA_DIR / "backups"

# Hoeveel automatische kopieën er blijven staan. Handmatige kopieën en die van
# vóór een terugzetting worden nooit opgeruimd: dat zijn net de momenten waarop
# je terug wil kunnen.
AUTO_BEWAREN = 15

REDENEN = {
    "handmatig": "Met de hand gemaakt",
    "voor_herstel": "Vlak voor een terugzetting",
    "referentielijst": "Voor het inlezen van een referentielijst",
    "historiek": "Voor het inlezen van een historiek",
    "bestand": "Voor het inlezen van een bestand",
    "regels_opnieuw": "Voor het opnieuw toepassen van alle regels",
    "regels_uit_historiek": "Voor het afleiden van regels uit de historiek",
    "herindeling": "Voor een herindeling",
    "dagelijks": "Dagelijkse kopie",
    "wissen": "Voor het leegmaken van de databank",
}

BLIJVEND = {"handmatig", "voor_herstel", "wissen"}

_NAAM = re.compile(r"^(\d{8}-\d{6})_([a-z_]+)\.db$")


@dataclass
class Kopie:
    pad: Path
    tijdstip: datetime
    reden: str
    bytes: int

    @property
    def naam(self) -> str:
        return self.pad.name

    @property
    def omschrijving(self) -> str:
        return REDENEN.get(self.reden, self.reden.replace("_", " "))

    @property
    def blijvend(self) -> bool:
        return self.reden in BLIJVEND

    @property
    def mb(self) -> float:
        return round(self.bytes / (1024 * 1024), 2)


def maak(reden: str = "handmatig") -> Kopie | None:
    """Legt een kopie van de databank. Geeft None als dat niet lukt.

    Een mislukte kopie mag de handeling erna nooit tegenhouden: liever de
    ingreep zonder vangnet dan een toepassing die niets meer doet. De aanroeper
    krijgt None terug en kan dat melden.
    """
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    nu = datetime.now(timezone.utc)
    doel = BACKUP_DIR / f"{nu.strftime('%Y%m%d-%H%M%S')}_{_veilig(reden)}.db"
    if doel.exists():
        return _als_kopie(doel)
    try:
        bron = sqlite3.connect(DB_PATH)
        try:
            bron.execute("VACUUM INTO ?", (str(doel),))
        finally:
            bron.close()
    except sqlite3.Error:
        try:
            doel.unlink()
        except OSError:
            pass
        return None
    ruim_op()
    return _als_kopie(doel)


def lijst() -> list[Kopie]:
    """Alle kopieën, de nieuwste eerst."""
    if not BACKUP_DIR.exists():
        return []
    kopieen = [k for k in (_als_kopie(p) for p in BACKUP_DIR.glob("*.db")) if k]
    return sorted(kopieen, key=lambda k: k.tijdstip, reverse=True)


def ruim_op(bewaren: int = AUTO_BEWAREN) -> int:
    """Gooit de oudste automatische kopieën weg. Geeft het aantal terug."""
    automatisch = [k for k in lijst() if not k.blijvend]
    weg = 0
    for kopie in automatisch[bewaren:]:
        try:
            kopie.pad.unlink()
            weg += 1
        except OSError:
            pass
    return weg


def vandaag_al_een() -> bool:
    """Staat er vandaag al een kopie? Om er niet bij elke klik een te maken."""
    vandaag = datetime.now(timezone.utc).date()
    return any(k.tijdstip.date() == vandaag for k in lijst())


def dagelijks() -> Kopie | None:
    """Eén kopie per dag, bij de eerste handeling die erom vraagt."""
    if vandaag_al_een():
        return None
    return maak("dagelijks")


def zoek(naam: str) -> Kopie | None:
    """Zoekt een kopie op bestandsnaam, zonder buiten de backupmap te kijken."""
    if _NAAM.match(naam) is None:
        return None
    pad = BACKUP_DIR / naam
    try:
        if pad.resolve().parent != BACKUP_DIR.resolve() or not pad.exists():
            return None
    except OSError:
        return None
    return _als_kopie(pad)


def herstel(kopie: Kopie) -> bool:
    """Zet deze kopie terug als de werkende databank.

    Er wordt eerst een kopie van de huidige toestand gelegd, zodat ook het
    terugzetten zelf ongedaan te maken is.

    Het gaat via de backup-API van SQLite en niet via een bestandskopie. Dat
    scheelt: de API schrijft ín de bestaande databank, met de vergrendeling die
    daarbij hoort, zodat verbindingen die op dat moment openstaan gewoon de
    nieuwe inhoud zien. Een bestand eroverheen kopiëren en het WAL-bestand
    weggooien laat die verbindingen achter bij een databank die niet meer
    bestaat.
    """
    if not kopie.pad.exists():
        return False
    maak("voor_herstel")
    bron = doel = None
    try:
        bron = sqlite3.connect(kopie.pad)
        doel = sqlite3.connect(DB_PATH)
        bron.backup(doel)
        doel.commit()
    except sqlite3.Error:
        return False
    finally:
        for verbinding in (bron, doel):
            if verbinding is not None:
                verbinding.close()
    return True


def verwijder(kopie: Kopie) -> bool:
    try:
        kopie.pad.unlink()
        return True
    except OSError:
        return False


def _veilig(reden: str) -> str:
    schoon = re.sub(r"[^a-z_]", "", reden.lower().replace("-", "_"))
    return schoon or "handmatig"


def _als_kopie(pad: Path) -> Kopie | None:
    treffer = _NAAM.match(pad.name)
    if treffer is None:
        return None
    try:
        tijdstip = datetime.strptime(treffer.group(1), "%Y%m%d-%H%M%S").replace(
            tzinfo=timezone.utc)
        grootte = pad.stat().st_size
    except (ValueError, OSError):
        return None
    return Kopie(pad=pad, tijdstip=tijdstip, reden=treffer.group(2), bytes=grootte)
