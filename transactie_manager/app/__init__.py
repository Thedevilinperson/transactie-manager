"""Transactie Manager — huishoudboekje op basis van bankafschriften."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from flask import Flask, g, redirect, request, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import APP_NAME, MAX_UPLOAD_MB, SESSION_MINUTES, VERSION, flask_secret_key
from .database import close_db, heeft_gebruikers, init_db

__version__ = VERSION


class Ingress:
    """Zorgt dat de toepassing werkt achter het ingress-pad van Home Assistant.

    Home Assistant zet de add-on achter een adres als
    `/api/hassio_ingress/<token>/`. De Supervisor knipt dat voorvoegsel er
    weer af voor hij de aanvraag doorstuurt, maar geeft het mee in de kop
    `X-Ingress-Path`. Zonder die kop te lezen maakt Flask paden vanaf de
    wortel, en die kent Home Assistant niet: het antwoord is dan een 404 van
    Home Assistant zelf, nog voor de toepassing iets te zien krijgt.

    Door het voorvoegsel in `SCRIPT_NAME` te zetten, neemt `url_for` het
    vanzelf mee in elke verwijzing, omleiding en formulieractie.
    """

    def __init__(self, toepassing):
        self.toepassing = toepassing

    def __call__(self, omgeving, start_antwoord):
        voorvoegsel = (omgeving.get("HTTP_X_INGRESS_PATH") or "").rstrip("/")
        if voorvoegsel:
            omgeving["SCRIPT_NAME"] = voorvoegsel
            pad = omgeving.get("PATH_INFO", "")
            # Normaal is het voorvoegsel er al af; dit vangt op wanneer een
            # andere omgekeerde proxy het wel laat staan.
            if pad.startswith(voorvoegsel):
                omgeving["PATH_INFO"] = pad[len(voorvoegsel):] or "/"
        return self.toepassing(omgeving, start_antwoord)


def veilig_terug(waarde: str | None, standaard: str) -> str:
    """Maakt van een meegegeven pad een adres binnen deze toepassing.

    Twee dingen gaan hier mis als je het niet doet. Achter de ingress van Home
    Assistant draait de toepassing onder een voorvoegsel; een pad als
    `/transacties/` wijst dan niet naar de add-on maar naar Home Assistant zelf,
    dat vervolgens binnen het venster van de add-on opent. En een meegegeven
    pad mag nooit naar een andere site kunnen wijzen.
    """
    if not waarde or not waarde.startswith("/") or waarde.startswith("//"):
        return standaard
    wortel = request.script_root or ""
    if wortel and not (waarde == wortel or waarde.startswith(wortel + "/")):
        waarde = wortel + waarde
    return waarde


def huidig_pad() -> str:
    """Het volledige adres van de huidige bladzijde, voorvoegsel inbegrepen."""
    return (request.script_root or "") + request.full_path


def _scheid(tekst: str) -> str:
    """Van de Engelse opmaak 1,234.56 naar de onze: 1.234,56."""
    return tekst.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def euro(waarde) -> str:
    """Bedrag met muntteken, punt als duizendtalscheiding: €1.200,50."""
    if waarde in (None, ""):
        return "—"
    getal = Decimal(str(waarde))
    return ("-" if getal < 0 else "") + "€" + _scheid(f"{abs(getal):,.2f}")


def euro_rond(waarde) -> str:
    """Hele euro's, zonder decimalen en zonder overbodige nullen."""
    if waarde in (None, ""):
        return "—"
    getal = Decimal(str(waarde)).quantize(Decimal("1"))
    if getal == 0:
        return "—"
    return ("-" if getal < 0 else "") + "€" + _scheid(f"{abs(getal):,}")


def datum_kort(waarde) -> str:
    if not waarde:
        return ""
    tekst = str(waarde)[:10]
    delen = tekst.split("-")
    return f"{delen[2]}/{delen[1]}/{delen[0]}" if len(delen) == 3 else tekst


def procent(waarde) -> str:
    try:
        return f"{float(waarde) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=flask_secret_key(),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSION_MINUTES),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # De adressen dragen het versienummer, dus mag er lang gecachet worden.
        SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=7),
        JSON_SORT_KEYS=False,
    )

    # Achter de ingress-proxy van Home Assistant.
    app.wsgi_app = Ingress(ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1))

    init_db()

    app.jinja_env.filters["euro"] = euro
    app.jinja_env.filters["euro0"] = euro_rond
    app.jinja_env.filters["datum"] = datum_kort
    app.jinja_env.filters["procent"] = procent
    app.jinja_env.globals["huidig_pad"] = huidig_pad

    def zonder_filter(sleutel: str, waarde=None) -> dict:
        """De huidige adresparameters, met één filterwaarde eruit gehaald.

        Daarmee kan elke actieve keuze apart weggeklikt worden, in plaats van
        alles in één keer te moeten wissen.
        """
        args = request.args.to_dict(flat=False)
        if sleutel in args:
            if waarde is None:
                args.pop(sleutel)
            else:
                rest = [v for v in args[sleutel] if v != str(waarde)]
                if rest:
                    args[sleutel] = rest
                else:
                    args.pop(sleutel)
        args.pop("pagina", None)
        return args

    app.jinja_env.globals["zonder_filter"] = zonder_filter

    @app.route("/statisch/<versie>/<path:bestand>")
    def statisch_bestand(versie: str, bestand: str):
        """Stijlblad en script, met het versienummer in het pad.

        Het versienummer zit bewust in het pad en niet in een parameter erachter.
        Een tussenliggende proxy of een service worker die op het pad bewaart,
        negeert zo'n parameter en blijft dan het bestand van de vorige versie
        teruggeven. Dat levert schermen op die half werken: de bladzijde van
        vandaag met de opmaak van gisteren. Met het nummer in het pad is elke
        versie een ander adres en kan dat niet gebeuren.
        """
        antwoord = send_from_directory(app.static_folder, bestand)
        if versie == VERSION:
            antwoord.headers["Cache-Control"] = "public, max-age=2592000, immutable"
        else:
            antwoord.headers["Cache-Control"] = "no-store"
        return antwoord

    def statisch(bestand: str) -> str:
        return url_for("statisch_bestand", versie=VERSION, bestand=bestand)

    app.jinja_env.globals["statisch"] = statisch

    @app.after_request
    def _geen_cache_op_schermen(antwoord):
        """Schermen zelf mogen nergens bewaard worden.

        Anders kan een proxy een bladzijde van een vorige versie teruggeven, die
        dan naar bestanden verwijst die intussen niet meer bestaan.
        """
        if request.endpoint not in ("static", "statisch_bestand"):
            antwoord.headers.setdefault(
                "Cache-Control", "no-store, no-cache, must-revalidate")
            antwoord.headers.setdefault("Pragma", "no-cache")
        return antwoord

    from .routes import aanmelden, bijzonder, dashboard, importeren, instellingen
    from .routes import koppelvlak
    from .routes import rapporten as rapport_routes
    from .routes import transacties as tx_routes

    app.register_blueprint(aanmelden.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(tx_routes.bp)
    app.register_blueprint(importeren.bp)
    app.register_blueprint(instellingen.bp)
    app.register_blueprint(rapport_routes.bp)
    app.register_blueprint(koppelvlak.bp)
    app.register_blueprint(bijzonder.bp)

    app.teardown_appcontext(close_db)

    @app.before_request
    def _eerste_start():
        from flask import request
        if request.endpoint in (None, "static", "statisch_bestand", "auth.installatie"):
            return None
        if not heeft_gebruikers():
            return redirect(url_for("auth.installatie"))
        return None

    @app.context_processor
    def _gedeeld():
        return {
            "app_naam": APP_NAME,
            "versie": VERSION,
            "gebruiker": getattr(g, "gebruiker", None),
            "is_beheerder": getattr(g, "sessie", {}).get("beheerder", False)
            if hasattr(g, "sessie") else False,
        }

    return app
