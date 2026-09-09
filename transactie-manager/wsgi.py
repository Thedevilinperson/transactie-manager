"""Ingangspunt voor een WSGI-server (waitress, gunicorn, ...)."""

from app import create_app

application = create_app()
app = application
