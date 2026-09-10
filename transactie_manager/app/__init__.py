"""Transactie Manager — huishoudboekje op basis van bankafschriften."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from flask import Flask, g, redirect, url_for

from .config import APP_NAME, MAX_UPLOAD_MB, SESSION_MINUTES, VERSION, flask_secret_key
from .database import close_db, heeft_gebruikers, init_db

__version__ = VERSION


def euro(waarde) -> str:
    if waarde in (None, ""):
        return "—"
    getal = Decimal(str(waarde))
    tekst = f"{abs(getal):,.2f}".replace(",", "\u00a0").replace(".", ",")
    return ("-" if getal < 0 else "") + tekst


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
        JSON_SORT_KEYS=False,
    )

    init_db()

    app.jinja_env.filters["euro"] = euro
    app.jinja_env.filters["datum"] = datum_kort
    app.jinja_env.filters["procent"] = procent

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
        if request.endpoint in (None, "static", "auth.installatie"):
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
