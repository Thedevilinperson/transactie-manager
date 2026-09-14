"""Verzenden van e-mail via een SMTP-server.

Getest tegen Yahoo Mail. Let op: Yahoo aanvaardt je gewone wachtwoord niet meer
voor SMTP. Je moet in je Yahoo-account onder *Accountbeveiliging* een
app-wachtwoord van zestien tekens aanmaken en dat hier invullen.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import lokaal

TIMEOUT = 20


class MailFout(RuntimeError):
    pass


def instellingen(conn) -> dict:
    return {
        sleutel: lokaal.lees(conn, sleutel, standaard)
        for sleutel, standaard in lokaal.STANDAARD.items()
    }


def actief(conn) -> bool:
    waarden = instellingen(conn)
    return (waarden["smtp_actief"] == "1"
            and bool(waarden["smtp_server"])
            and bool(waarden["smtp_gebruiker"]))


def _afzender(waarden: dict) -> str:
    return waarden["smtp_afzender"] or waarden["smtp_gebruiker"]


def verstuur(conn, naar: str, onderwerp: str, tekst: str) -> None:
    waarden = instellingen(conn)
    if not waarden["smtp_server"] or not naar:
        raise MailFout("De mailserver is nog niet ingesteld.")

    bericht = EmailMessage()
    bericht["From"] = _afzender(waarden)
    bericht["To"] = naar
    bericht["Subject"] = onderwerp
    bericht["Date"] = formatdate(localtime=True)
    bericht["Message-ID"] = make_msgid(domain="transactie-manager.local")
    bericht.set_content(tekst)

    poort = int(waarden["smtp_poort"] or 465)
    beveiliging = waarden["smtp_beveiliging"]
    context = ssl.create_default_context()

    try:
        if beveiliging == "ssl":
            server = smtplib.SMTP_SSL(waarden["smtp_server"], poort,
                                      timeout=TIMEOUT, context=context)
        else:
            server = smtplib.SMTP(waarden["smtp_server"], poort, timeout=TIMEOUT)
        with server:
            server.ehlo()
            if beveiliging == "starttls":
                server.starttls(context=context)
                server.ehlo()
            if waarden["smtp_gebruiker"]:
                server.login(waarden["smtp_gebruiker"], waarden["smtp_wachtwoord"])
            server.send_message(bericht)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailFout(
            "De mailserver weigert de aanmelding. Bij Yahoo moet je een "
            "app-wachtwoord gebruiken, niet je gewone wachtwoord. "
            f"Antwoord van de server: {exc.smtp_error.decode(errors='replace')[:120]}"
        ) from exc
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise MailFout(f"Versturen is niet gelukt: {exc}") from exc


def verstuur_testbericht(conn, naar: str) -> None:
    verstuur(
        conn, naar,
        "Testbericht van Transactie Manager",
        "Dit is een testbericht.\n\n"
        "Krijg je dit te zien, dan staan je mailinstellingen goed en kan de "
        "toepassing je een herstelcode sturen wanneer je je wachtwoord vergeet.\n",
    )


def verstuur_herstelcode(conn, naar: str, gebruikersnaam: str, code: str,
                         geldig_minuten: int) -> None:
    verstuur(
        conn, naar,
        "Herstelcode voor Transactie Manager",
        f"Er is een wachtwoordherstel aangevraagd voor het account "
        f"{gebruikersnaam}.\n\n"
        f"Je code is: {code}\n\n"
        f"De code blijft {geldig_minuten} minuten geldig.\n\n"
        "Naast deze code heb je ook je herstelsleutel nodig, die je bij de "
        "installatie hebt opgeschreven. Zonder die sleutel kunnen je gegevens "
        "niet ontsleuteld worden, ook niet met deze code.\n\n"
        "Heb je dit niet zelf aangevraagd, dan hoef je niets te doen. Met deze "
        "code alleen kan niemand bij je gegevens.\n",
    )
