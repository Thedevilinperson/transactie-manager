"""Instellingen die leesbaar moeten zijn vóór iemand aangemeld is.

Voor het versturen van een herstelcode is er een probleem van volgorde: je hebt
de SMTP-gegevens en het e-mailadres nodig op een moment dat er nog niemand
aangemeld is, en dus geen datasleutel in het geheugen zit. Die gegevens kunnen
daarom niet met de datasleutel versleuteld worden.

Ze staan versleuteld met een aparte sleutel die naast de databank op schijf
ligt, in `lokaal.key`. Dat beschermt tegen een losse kopie van het
databankbestand, niet tegen iemand die bij de hele datamap kan. Het gaat hier
bewust alleen om het adres waarnaar een code gestuurd wordt en het
app-wachtwoord van de mailserver — niet om je financiële gegevens. Die blijven
versleuteld met de sleutel die alleen jouw wachtwoord of je herstelsleutel
opent.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import DATA_DIR

SLEUTELBESTAND = DATA_DIR / "lokaal.key"
NONCE_LEN = 12


def _sleutel() -> bytes:
    if SLEUTELBESTAND.exists():
        return SLEUTELBESTAND.read_bytes()
    sleutel = os.urandom(32)
    SLEUTELBESTAND.write_bytes(sleutel)
    try:
        os.chmod(SLEUTELBESTAND, 0o600)
    except OSError:
        pass
    return sleutel


def versleutel(waarde: str | None) -> str | None:
    if waarde in (None, ""):
        return None
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(_sleutel()).encrypt(nonce, str(waarde).encode("utf-8"), b"lokaal")
    return base64.b64encode(nonce + ct).decode("ascii")


def ontsleutel(blob: str | None) -> str | None:
    if blob in (None, ""):
        return None
    try:
        ruw = base64.b64decode(blob)
        return AESGCM(_sleutel()).decrypt(ruw[:NONCE_LEN], ruw[NONCE_LEN:],
                                          b"lokaal").decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def lees(conn, sleutel: str, standaard: str = "") -> str:
    rij = conn.execute(
        "SELECT waarde_lok FROM lokale_instellingen WHERE sleutel = ?", (sleutel,)
    ).fetchone()
    if rij is None:
        return standaard
    return ontsleutel(rij["waarde_lok"]) or standaard


def schrijf(conn, sleutel: str, waarde: str) -> None:
    conn.execute(
        "INSERT INTO lokale_instellingen (sleutel, waarde_lok) VALUES (?, ?) "
        "ON CONFLICT(sleutel) DO UPDATE SET waarde_lok = excluded.waarde_lok",
        (sleutel, versleutel(waarde)),
    )


STANDAARD = {
    "smtp_actief": "0",
    "smtp_server": "smtp.mail.yahoo.com",
    "smtp_poort": "465",
    "smtp_beveiliging": "ssl",   # ssl | starttls | geen
    "smtp_gebruiker": "",
    "smtp_wachtwoord": "",
    "smtp_afzender": "",
}
