"""Gedeelde filters voor de transactielijst, de jaartabel en de grafieken.

Alle schermen werken met dezelfde begrippen: jaren, richting, rekening,
categorie, land, winkel en status. Die worden hier één keer uitgelezen uit de
adresbalk en één keer toegepast, zodat een filter overal hetzelfde betekent.

Land en winkel staan versleuteld in de databank, dus daarop kan niet met SQL
gefilterd worden. Die twee worden na het ontsleutelen in het geheugen
afgehandeld. De lijst met beschikbare waarden wordt in het proces bewaard en
pas opnieuw opgebouwd wanneer er transacties bijkomen of veranderen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from flask import request

from .crypto import normalize

# Waarden die in de databank "niet ingevuld" betekenen.
LEEG = "—"

# Waarden die in de gegevens "niets ingevuld" betekenen en dus geen echte
# winkel of land zijn.
ZONDER_WAARDE = {"-", "--", "?", "n/a", "nvt", "geen", "."}

METHODEN = [
    ("regel", "Vaste regel"),
    ("fuzzy", "Gelijkenis"),
    ("ai", "AI-model"),
    ("bestand", "Uit het bestand"),
    ("manueel", "Met de hand"),
    ("geen", "Niets gevonden"),
]

STATUSSEN = [
    ("bevestigd", "Bevestigd"),
    ("nazicht", "Nazicht"),
    ("niet_toegewezen", "Zonder categorie"),
]


@dataclass
class Filters:
    jaren: list[int] = field(default_factory=list)
    richting: str = ""
    rekening_id: int | None = None
    categorie_id: int | None = None
    hoofd_id: int | None = None
    sub_id: int | None = None
    subsub_id: int | None = None
    landen: list[str] = field(default_factory=list)
    winkels: list[str] = field(default_factory=list)
    methoden: list[str] = field(default_factory=list)
    status: str = ""
    zoekterm: str = ""
    alleen_bevestigd: bool = False
    # Uitsluiten, alleen gebruikt bij de grafieken.
    uit_winkels: list[str] = field(default_factory=list)
    uit_landen: list[str] = field(default_factory=list)
    uit_categorieen: list[int] = field(default_factory=list)
    groepering: str = "hoofd"      # hoofd | sub | subsub | land | winkel
    periode: str = "jaar"          # jaar | maand

    @classmethod
    def uit_aanvraag(cls, standaard_richting: str = "") -> "Filters":
        arg = request.args
        hoofd = arg.get("hoofd_id", type=int)
        sub = arg.get("sub_id", type=int)
        subsub = arg.get("subsub_id", type=int)
        return cls(
            jaren=[int(j) for j in arg.getlist("jaar") if j.isdigit()],
            richting=arg.get("richting", standaard_richting),
            rekening_id=arg.get("rekening_id", type=int),
            categorie_id=subsub or sub or hoofd,
            hoofd_id=hoofd, sub_id=sub, subsub_id=subsub,
            landen=[w for w in arg.getlist("land") if w],
            winkels=[w for w in arg.getlist("winkel") if w],
            methoden=[m for m in arg.getlist("methode") if m],
            status=arg.get("status", ""),
            zoekterm=arg.get("q", "").strip(),
            alleen_bevestigd=arg.get("alleen_bevestigd") == "1",
            uit_winkels=[w for w in arg.getlist("uit_winkel") if w],
            uit_landen=[w for w in arg.getlist("uit_land") if w],
            uit_categorieen=[int(c) for c in arg.getlist("uit_categorie") if c.isdigit()],
            groepering=arg.get("groepering", "hoofd"),
            periode=arg.get("periode", "jaar"),
        )

    # -- SQL-gedeelte -------------------------------------------------------
    def sql(self, *, alleen_ingedeeld: bool = False,
            met_richting: bool = True) -> tuple[str, list]:
        """Bouwt het WHERE-gedeelte.

        `met_richting` bepaalt of de richting als filter op de rijen geldt. In
        een lijst van transacties hoort dat zo: vraag je om uitgaven, dan wil je
        geen inkomsten zien. In een overzicht per categorie hoort dat net niet:
        daar moet een terugbetaling of een tegenboeking van de uitgave áfgaan.
        Zou je die rijen wegfilteren, dan blijft de uitgave voor het volle bedrag
        staan terwijl ze teruggedraaid is.
        """
        stukken = ["is_afrekening = 0"]
        params: list = []
        if alleen_ingedeeld:
            stukken.append("categorie_id IS NOT NULL")
        if met_richting and self.richting in ("in", "uit"):
            stukken.append("richting = ?")
            params.append(self.richting)
        if self.rekening_id:
            stukken.append("rekening_id = ?")
            params.append(self.rekening_id)
        if self.jaren:
            stukken.append(
                f"substr(boekdatum, 1, 4) IN ({','.join('?' * len(self.jaren))})")
            params += [str(j) for j in self.jaren]
        if self.status:
            stukken.append("status = ?")
            params.append(self.status)
        elif self.alleen_bevestigd:
            stukken.append("status = 'bevestigd'")
        if self.methoden:
            stukken.append(f"methode IN ({','.join('?' * len(self.methoden))})")
            params += self.methoden
        return " AND ".join(stukken), params

    # -- gedeelte dat ontsleuteling vraagt ----------------------------------
    @property
    def vraagt_tekst(self) -> bool:
        return bool(self.landen or self.winkels or self.uit_winkels
                    or self.uit_landen or self.zoekterm)

    def past_tekst(self, *, land: str = "", winkel: str = "") -> bool:
        if self.landen and (land or LEEG) not in self.landen:
            return False
        if self.winkels and (winkel or LEEG) not in self.winkels:
            return False
        if self.uit_winkels and (winkel or LEEG) in self.uit_winkels:
            return False
        if self.uit_landen and (land or LEEG) in self.uit_landen:
            return False
        return True

    def past_categorie(self, cat_ids: set, toegelaten: set | None) -> bool:
        if toegelaten is not None and not (cat_ids & toegelaten):
            return False
        if self.uit_categorieen and (cat_ids & set(self.uit_categorieen)):
            return False
        return True

    # -- adresbalk ----------------------------------------------------------
    def zonder(self, *sleutels: str) -> dict:
        """De huidige filters als woordenboek, zonder de genoemde sleutels."""
        uit = {k: v for k, v in request.args.lists() if k not in sleutels}
        return uit


# --------------------------------------------------------------------------
# Beschikbare waarden voor de keuzelijsten
# --------------------------------------------------------------------------

_cache: dict = {}


def _stempel(conn) -> tuple:
    rij = conn.execute(
        "SELECT COUNT(*) n, IFNULL(MAX(gewijzigd_op), '') m FROM transacties").fetchone()
    return (rij["n"], rij["m"])


def keuzes(conn, crypto) -> dict:
    """Jaren, landen en winkels die in de databank voorkomen.

    Deze lijst kost een ontsleuteling per transactie, dus ze wordt bewaard tot
    er iets aan de transacties verandert.
    """
    stempel = _stempel(conn)
    if _cache.get("stempel") == stempel:
        return _cache["waarden"]

    jaren: set[int] = set()
    landen: dict[str, int] = {}
    winkels: dict[str, int] = {}

    for row in conn.execute(
        "SELECT boekdatum, land_enc, handelaar_enc FROM transacties WHERE is_afrekening = 0"
    ):
        jaren.add(int(row["boekdatum"][:4]))
        land = (crypto.dec(row["land_enc"]) or "").strip()
        if land and land not in ZONDER_WAARDE:
            landen[land] = landen.get(land, 0) + 1
        winkel = (crypto.dec(row["handelaar_enc"]) or "").strip()
        if winkel and winkel not in ZONDER_WAARDE:
            winkels[winkel] = winkels.get(winkel, 0) + 1

    # Alfabetisch: in een lijst van honderden winkels zoek je op naam, niet op
    # hoe vaak iets voorkomt.
    waarden = {
        "jaren": sorted(jaren, reverse=True),
        "landen": sorted(landen.items(), key=lambda p: p[0].lower()),
        "winkels": sorted(winkels.items(), key=lambda p: p[0].lower()),
    }
    _cache["stempel"] = stempel
    _cache["waarden"] = waarden
    return waarden


def vergeet_keuzes() -> None:
    _cache.clear()


def rekeningen(conn, crypto) -> list[dict]:
    lijst = [
        {"id": r["id"], "naam": crypto.dec(r["naam_enc"]) or ""}
        for r in conn.execute("SELECT * FROM rekeningen")
    ]
    return sorted(lijst, key=lambda r: r["naam"].lower())
