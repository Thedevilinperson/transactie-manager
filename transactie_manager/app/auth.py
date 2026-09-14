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
from . import lokaal
from .config import SESSION_MINUTES
from .database import connect, now_iso

HERSTELCODE_MINUTEN = 15
HERSTELCODE_POGINGEN = 5

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


# --------------------------------------------------------------------------
# Herstel: sleutel en code
# --------------------------------------------------------------------------

def zet_herstelsleutel(gebruiker_id: int, dek: bytes) -> str:
    """Maakt een nieuwe herstelsleutel en bewaart er een tweede ingepakte
    kopie van de datasleutel mee. Geeft de sleutel één keer terug; hij wordt
    nergens leesbaar opgeslagen."""
    sleutel = cryptomod.nieuwe_herstelsleutel()
    genormaliseerd = cryptomod.normaliseer_herstelsleutel(sleutel)
    salt = cryptomod.new_salt()
    kek = cryptomod.derive_kek(genormaliseerd, salt)
    conn = connect()
    try:
        conn.execute(
            "UPDATE gebruikers SET herstel_salt=?, herstel_verif=?, herstel_wrapped=?,"
            " herstel_op=? WHERE id=?",
            (salt, _verificatie(kek), cryptomod.wrap_dek(dek, kek), now_iso(), gebruiker_id),
        )
        conn.commit()
    finally:
        conn.close()
    return sleutel


def zet_herstelmail(gebruiker_id: int, adres: str) -> None:
    conn = connect()
    try:
        conn.execute("UPDATE gebruikers SET email_lok=? WHERE id=?",
                     (lokaal.versleutel(adres.strip()) if adres.strip() else None,
                      gebruiker_id))
        conn.commit()
    finally:
        conn.close()


def herstelstatus(gebruiker_id: int) -> dict:
    conn = connect()
    try:
        rij = conn.execute(
            "SELECT herstel_wrapped, herstel_op, email_lok FROM gebruikers WHERE id=?",
            (gebruiker_id,)).fetchone()
    finally:
        conn.close()
    if rij is None:
        return {"sleutel": False, "op": None, "email": ""}
    return {
        "sleutel": bool(rij["herstel_wrapped"]),
        "op": rij["herstel_op"],
        "email": lokaal.ontsleutel(rij["email_lok"]) or "",
    }


def maak_herstelcode(gebruiker_id: int) -> str:
    """Zes cijfers, versleuteld bewaard, een kwartier geldig."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = cryptomod.new_salt()
    verloopt = (datetime.now(timezone.utc)
                + timedelta(minutes=HERSTELCODE_MINUTEN)).replace(microsecond=0).isoformat()
    conn = connect()
    try:
        # Openstaande codes van dezelfde gebruiker vervallen.
        conn.execute("UPDATE herstel_codes SET gebruikt=1 WHERE gebruiker_id=? AND gebruikt=0",
                     (gebruiker_id,))
        conn.execute(
            "INSERT INTO herstel_codes (gebruiker_id, code_salt, code_hash, verloopt,"
            " aangemaakt_op) VALUES (?,?,?,?,?)",
            (gebruiker_id, salt, _verificatie(cryptomod.derive_kek(code, salt)),
             verloopt, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return code


def controleer_herstelcode(gebruiker_id: int, code: str) -> tuple[bool, str]:
    """Geeft (geldig, boodschap) terug en telt de pogingen mee."""
    conn = connect()
    try:
        rij = conn.execute(
            "SELECT * FROM herstel_codes WHERE gebruiker_id=? AND gebruikt=0"
            " ORDER BY id DESC LIMIT 1", (gebruiker_id,)).fetchone()
        if rij is None:
            return False, "Er staat geen code open. Vraag een nieuwe aan."
        if rij["verloopt"] < datetime.now(timezone.utc).replace(microsecond=0).isoformat():
            return False, "De code is verlopen. Vraag een nieuwe aan."
        if rij["pogingen"] >= HERSTELCODE_POGINGEN:
            conn.execute("UPDATE herstel_codes SET gebruikt=1 WHERE id=?", (rij["id"],))
            conn.commit()
            return False, "Te veel pogingen. Vraag een nieuwe code aan."

        kek = cryptomod.derive_kek((code or "").strip(), rij["code_salt"])
        if not hmac.compare_digest(_verificatie(kek), rij["code_hash"]):
            conn.execute("UPDATE herstel_codes SET pogingen=pogingen+1 WHERE id=?",
                         (rij["id"],))
            conn.commit()
            over = HERSTELCODE_POGINGEN - rij["pogingen"] - 1
            return False, f"De code klopt niet. Nog {max(over, 0)} pogingen over."
        return True, ""
    finally:
        conn.close()


def herstel_wachtwoord(gebruikersnaam: str, code: str, herstelsleutel: str,
                       nieuw_wachtwoord: str) -> tuple[bool, str]:
    """Zet een nieuw wachtwoord op basis van de herstelsleutel en de code."""
    conn = connect()
    try:
        rij = conn.execute(
            "SELECT * FROM gebruikers WHERE gebruikersnaam=? AND actief=1",
            (gebruikersnaam.strip(),)).fetchone()
    finally:
        conn.close()
    if rij is None or not rij["herstel_wrapped"]:
        return False, "Herstellen lukt niet voor dit account."

    goed, boodschap = controleer_herstelcode(rij["id"], code)
    if not goed:
        return False, boodschap

    genormaliseerd = cryptomod.normaliseer_herstelsleutel(herstelsleutel)
    if not genormaliseerd:
        return False, "Vul je herstelsleutel in."
    kek = cryptomod.derive_kek(genormaliseerd, rij["herstel_salt"])
    if not hmac.compare_digest(_verificatie(kek), rij["herstel_verif"]):
        return False, "De herstelsleutel klopt niet."
    try:
        dek = cryptomod.unwrap_dek(rij["herstel_wrapped"], kek)
    except Exception:  # noqa: BLE001
        return False, "De herstelsleutel klopt niet."

    wijzig_wachtwoord(rij["id"], nieuw_wachtwoord, dek)
    conn = connect()
    try:
        conn.execute("UPDATE herstel_codes SET gebruikt=1 WHERE gebruiker_id=?", (rij["id"],))
        conn.execute("INSERT INTO logboek (tijdstip, gebruiker, actie) VALUES (?,?,?)",
                     (now_iso(), rij["gebruikersnaam"], "wachtwoord_hersteld"))
        conn.commit()
    finally:
        conn.close()
    return True, ""
