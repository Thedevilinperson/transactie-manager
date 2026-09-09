"""Aanmelden, sessiebeheer en gebruikersbeheer.

De afgeleide datasleutel blijft in het geheugen van het proces en wordt nooit
in de cookie geplaatst. De cookie bevat enkel een willekeurig sessietoken.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import g, redirect, request, session, url_for

from . import crypto as cryptomod
from .config import SESSION_MINUTES
from .database import connect, now_iso

# token -> {"gebruiker": str, "id": int, "beheerder": bool, "crypto": Crypto, "verloopt": dt}
_SESSIES: dict[str, dict] = {}


def _verificatie(kek: bytes) -> str:
    """Waarde om een wachtwoord te controleren zonder de KEK op te slaan."""
    import hashlib
    return hashlib.sha256(b"verificatie|" + kek).hexdigest()


def maak_gebruiker(gebruikersnaam: str, wachtwoord: str, dek: bytes,
                   is_beheerder: bool = False) -> None:
    salt = cryptomod.new_salt()
    kek = cryptomod.derive_kek(wachtwoord, salt)
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO gebruikers (gebruikersnaam, pw_salt, pw_verif, dek_wrapped,"
            " is_beheerder, aangemaakt_op) VALUES (?,?,?,?,?,?)",
            (gebruikersnaam.strip(), salt, _verificatie(kek),
             cryptomod.wrap_dek(dek, kek), 1 if is_beheerder else 0, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def wijzig_wachtwoord(gebruiker_id: int, nieuw_wachtwoord: str, dek: bytes) -> None:
    salt = cryptomod.new_salt()
    kek = cryptomod.derive_kek(nieuw_wachtwoord, salt)
    conn = connect()
    try:
        conn.execute(
            "UPDATE gebruikers SET pw_salt=?, pw_verif=?, dek_wrapped=? WHERE id=?",
            (salt, _verificatie(kek), cryptomod.wrap_dek(dek, kek), gebruiker_id),
        )
        conn.commit()
    finally:
        conn.close()


def controleer_aanmelding(gebruikersnaam: str, wachtwoord: str):
    """Geeft (rij, dek) terug bij een geldige aanmelding, anders (None, None)."""
    conn = connect()
    try:
        rij = conn.execute(
            "SELECT * FROM gebruikers WHERE gebruikersnaam = ? AND actief = 1",
            (gebruikersnaam.strip(),),
        ).fetchone()
        if rij is None:
            # Even lang rekenen als bij een bestaande gebruiker.
            cryptomod.derive_kek(wachtwoord, cryptomod.new_salt())
            return None, None
        kek = cryptomod.derive_kek(wachtwoord, rij["pw_salt"])
        if not hmac.compare_digest(_verificatie(kek), rij["pw_verif"]):
            return None, None
        try:
            dek = cryptomod.unwrap_dek(rij["dek_wrapped"], kek)
        except Exception:
            return None, None
        conn.execute("UPDATE gebruikers SET laatste_login=? WHERE id=?", (now_iso(), rij["id"]))
        conn.commit()
        return rij, dek
    finally:
        conn.close()


def start_sessie(rij, dek: bytes) -> None:
    _opkuis()
    token = secrets.token_urlsafe(32)
    _SESSIES[token] = {
        "id": rij["id"],
        "gebruiker": rij["gebruikersnaam"],
        "beheerder": bool(rij["is_beheerder"]),
        "crypto": cryptomod.Crypto(dek),
        "dek": dek,
        "verloopt": datetime.now(timezone.utc) + timedelta(minutes=SESSION_MINUTES),
    }
    session.clear()
    session["token"] = token
    session.permanent = True


def beeindig_sessie() -> None:
    token = session.pop("token", None)
    if token:
        _SESSIES.pop(token, None)
    session.clear()


def _opkuis() -> None:
    nu = datetime.now(timezone.utc)
    for token in [t for t, s in _SESSIES.items() if s["verloopt"] < nu]:
        _SESSIES.pop(token, None)


def huidige_sessie():
    token = session.get("token")
    if not token:
        return None
    ses = _SESSIES.get(token)
    if ses is None:
        return None
    if ses["verloopt"] < datetime.now(timezone.utc):
        _SESSIES.pop(token, None)
        return None
    ses["verloopt"] = datetime.now(timezone.utc) + timedelta(minutes=SESSION_MINUTES)
    return ses


def login_vereist(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        ses = huidige_sessie()
        if ses is None:
            return redirect(url_for("auth.login", volgende=request.path))
        g.sessie = ses
        g.crypto = ses["crypto"]
        g.gebruiker = ses["gebruiker"]
        return view(*args, **kwargs)
    return wrapper


def beheerder_vereist(view):
    @wraps(view)
    @login_vereist
    def wrapper(*args, **kwargs):
        if not g.sessie["beheerder"]:
            return redirect(url_for("dashboard.index"))
        return view(*args, **kwargs)
    return wrapper
