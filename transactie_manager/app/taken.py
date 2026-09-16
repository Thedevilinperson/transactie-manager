"""Werk dat te lang duurt voor één aanvraag, met een voortgangsmeter.

Een invoer van tienduizenden rijen duurt te lang om de browser op te laten
wachten: die toont ondertussen een lege bladzijde en je weet niet of er iets
gebeurt. Zulk werk loopt daarom in een aparte draad, terwijl het scherm om de
zoveel tijd de stand opvraagt.

De taken staan in het geheugen van het proces. Na een herstart zijn ze weg; dat
is hier geen bezwaar, want elke taak schrijft zelf naar de databank en een
afgebroken invoer kan je gewoon opnieuw aanbieden — dubbels worden toch
overgeslagen.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

BEWAARTIJD = timedelta(hours=2)


@dataclass
class Taak:
    token: str
    omschrijving: str = ""
    fase: str = "Bezig met voorbereiden"
    stand: int = 0
    totaal: int = 0
    klaar: bool = False
    gelukt: bool = True
    fout: str = ""
    resultaat: dict = field(default_factory=dict)
    gestart: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    geeindigd: datetime | None = None

    @property
    def percent(self) -> int:
        if self.klaar:
            return 100
        if not self.totaal:
            return 0
        return min(99, int(self.stand * 100 / self.totaal))

    def vorder(self, stand: int, fase: str | None = None) -> None:
        self.stand = stand
        if fase:
            self.fase = fase

    def naar_json(self) -> dict:
        return {
            "fase": self.fase, "stand": self.stand, "totaal": self.totaal,
            "percent": self.percent, "klaar": self.klaar, "gelukt": self.gelukt,
            "fout": self.fout, "resultaat": self.resultaat,
            "seconden": int((
                (self.geeindigd or datetime.now(timezone.utc)) - self.gestart
            ).total_seconds()),
        }


_TAKEN: dict[str, Taak] = {}
_slot = threading.Lock()


def _opkuis() -> None:
    grens = datetime.now(timezone.utc) - BEWAARTIJD
    for token in [t for t, taak in _TAKEN.items()
                  if taak.klaar and (taak.geeindigd or taak.gestart) < grens]:
        _TAKEN.pop(token, None)


def start(token: str, omschrijving: str, werk, *args, **kwargs) -> Taak:
    """Zet `werk(taak, *args)` in een aparte draad en geeft de taak terug."""
    with _slot:
        _opkuis()
        taak = Taak(token=token, omschrijving=omschrijving)
        _TAKEN[token] = taak

    def loop():
        try:
            taak.resultaat = werk(taak, *args, **kwargs) or {}
        except Exception as exc:  # noqa: BLE001
            taak.gelukt = False
            taak.fout = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            taak.klaar = True
            taak.geeindigd = datetime.now(timezone.utc)
            if taak.gelukt:
                taak.fase = "Klaar"

    draad = threading.Thread(target=loop, name=f"taak-{token}", daemon=True)
    draad.start()
    return taak


def haal(token: str) -> Taak | None:
    return _TAKEN.get(token)
