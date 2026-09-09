"""Versleuteling van gegevens in rust.

Model
-----
* Uit het wachtwoord van de gebruiker wordt met scrypt een KEK (key encryption
  key) afgeleid.
* Er is één willekeurige DEK (data encryption key) van 32 bytes voor de hele
  databank. Elke gebruiker bewaart een eigen kopie van die DEK, versleuteld met
  zijn persoonlijke KEK. Zo kunnen meerdere gebruikers dezelfde gegevens lezen
  zonder dat de DEK ooit in klare tekst op schijf staat.
* Velden worden versleuteld met AES-256-GCM (nonce van 12 bytes vooraan).
* Voor velden waarop gezocht of ontdubbeld moet worden bestaat een "blind
  index": een HMAC-SHA256 van de genormaliseerde waarde. Die laat exacte
  vergelijking toe zonder de waarde zelf prijs te geven.

De DEK bestaat enkel in het geheugen van het draaiende proces, gekoppeld aan de
sessie van de aangemelde gebruiker. Na een herstart is opnieuw aanmelden nodig.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import unicodedata
from decimal import Decimal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
DEK_LEN = 32
NONCE_LEN = 12


# --------------------------------------------------------------------------
# Sleutelbeheer
# --------------------------------------------------------------------------

def new_salt(length: int = 16) -> bytes:
    return os.urandom(length)


def new_dek() -> bytes:
    return os.urandom(DEK_LEN)


def derive_kek(password: str, salt: bytes) -> bytes:
    """Leid een sleutel af uit het wachtwoord. Bewust traag."""
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DEK_LEN,
        maxmem=64 * 1024 * 1024,
    )


def wrap_dek(dek: bytes, kek: bytes) -> str:
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(kek).encrypt(nonce, dek, b"transactie-manager-dek")
    return base64.b64encode(nonce + ct).decode("ascii")


def unwrap_dek(wrapped: str, kek: bytes) -> bytes:
    raw = base64.b64decode(wrapped)
    return AESGCM(kek).decrypt(raw[:NONCE_LEN], raw[NONCE_LEN:], b"transactie-manager-dek")


# --------------------------------------------------------------------------
# Normalisatie
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]")


def normalize(value: str | None) -> str:
    """Kleine letters, zonder accenten, leestekens en dubbele spaties."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _NON_ALNUM.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_iban(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


# --------------------------------------------------------------------------
# Veldversleuteling
# --------------------------------------------------------------------------

class Crypto:
    """Versleutelt en ontsleutelt afzonderlijke databankvelden."""

    def __init__(self, dek: bytes):
        self._dek = dek
        self._aes = AESGCM(dek)
        self._index_key = hashlib.sha256(b"blind-index|" + dek).digest()

    # -- symmetrische velden -----------------------------------------------
    def enc(self, value, aad: bytes = b"veld") -> str | None:
        if value is None:
            return None
        nonce = os.urandom(NONCE_LEN)
        ct = self._aes.encrypt(nonce, str(value).encode("utf-8"), aad)
        return base64.b64encode(nonce + ct).decode("ascii")

    def dec(self, blob, aad: bytes = b"veld") -> str | None:
        if blob is None:
            return None
        raw = base64.b64decode(blob)
        return self._aes.decrypt(raw[:NONCE_LEN], raw[NONCE_LEN:], aad).decode("utf-8")

    # -- bedragen -----------------------------------------------------------
    def enc_amount(self, value: Decimal | float | str) -> str:
        return self.enc(f"{Decimal(str(value)):.2f}", aad=b"bedrag")

    def dec_amount(self, blob) -> Decimal:
        if blob is None:
            return Decimal("0.00")
        return Decimal(self.dec(blob, aad=b"bedrag"))

    # -- blinde index -------------------------------------------------------
    def blind(self, value: str | None, *, iban: bool = False) -> str | None:
        if value is None:
            return None
        text = normalize_iban(value) if iban else normalize(value)
        if not text:
            return None
        return hmac.new(self._index_key, text.encode("utf-8"), hashlib.sha256).hexdigest()

    def fingerprint(self, *parts) -> str:
        """Stabiele vingerafdruk over meerdere velden, voor ontdubbeling."""
        joined = "|".join(normalize(p) for p in parts)
        return hmac.new(self._index_key, joined.encode("utf-8"), hashlib.sha256).hexdigest()
