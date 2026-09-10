"""Categorisatie in vier stappen: vaste regels, fuzzy logica, AI, manueel."""

from .engine import Motor, TransactieKenmerken, Voorstel, laad_regels, regel_past

__all__ = ["Motor", "TransactieKenmerken", "Voorstel", "laad_regels", "regel_past"]
