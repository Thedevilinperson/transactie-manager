"""Configuratie en paden."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

APP_NAME = "Transactie Manager"
VERSION = "0.2.1"

BASE_DIR = Path(__file__).resolve().parent.parent

# In de Home Assistant add-on wijst TM_DATA_DIR naar /data zodat gegevens
# een herinstallatie overleven. Lokaal op Windows is dat ./data.
DATA_DIR = Path(os.environ.get("TM_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("TM_DB_PATH", DATA_DIR / "transacties.db"))

HOST = os.environ.get("TM_HOST", "0.0.0.0")
PORT = int(os.environ.get("TM_PORT", "8099"))

# Sessieduur in minuten; daarna moet opnieuw worden aangemeld.
SESSION_MINUTES = int(os.environ.get("TM_SESSION_MINUTES", "120"))

MAX_UPLOAD_MB = int(os.environ.get("TM_MAX_UPLOAD_MB", "25"))


def flask_secret_key() -> bytes:
    """Blijvende sleutel voor het ondertekenen van de sessiecookie."""
    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_bytes()
    key = secrets.token_bytes(32)
    key_file.write_bytes(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


# Standaardwaarden voor instellingen die in de databank staan.
DEFAULT_SETTINGS = {
    "fuzzy_auto_drempel": "92",
    "fuzzy_suggestie_drempel": "72",
    "ai_actief": "0",
    "ai_basis_url": "http://homeassistant.local:11434",
    "ai_model": "llama3.1:8b",
    "ai_zoeken_actief": "0",
    "ai_zoek_url": "https://duckduckgo.com/html/?q=",
    "munt": "EUR",
    "leer_van_bevestiging": "1",
}
