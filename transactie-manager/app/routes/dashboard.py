"""Startscherm met kerncijfers."""

from __future__ import annotations

from flask import Blueprint, g, render_template

from ..auth import login_vereist
from ..database import get_db
from ..rapporten import kerncijfers
from ..transacties import zoek

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_vereist
def index():
    conn = get_db()
    cijfers = kerncijfers(conn, g.crypto)
    recent = zoek(conn, g.crypto, limiet=8)
    return render_template("dashboard.html", cijfers=cijfers, recent=recent)
