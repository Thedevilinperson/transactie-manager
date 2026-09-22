"""Wat het AI-model uit je eigen historiek leert.

Een klein taalmodel kent jouw indeling niet. "Restaurant" onder "Hobby", of
"2dehands verkoop" onder "Kledij": dat zijn persoonlijke keuzes, en zonder
voorbeelden raadt een model de gangbare betekenis. Deze module haalt die
voorbeelden uit wat je zelf al bevestigd hebt:

* **welke paden je per richting gebruikt**, en hoe vaak — ook tussenniveaus
  zoals *Hobby › restaurant* waar je rechtstreeks in indeelt, terwijl er
  subcategorieën onder hangen;
* **met welke tegenpartijen** je elk pad vult, zodat het model ziet wat een
  categorie voor jou betekent;
* **welke eerdere transacties op een nieuwe lijken**, op basis van de woorden
  in tegenpartij en mededeling. Zeldzame woorden ("chiro", "donkere toren")
  wegen zwaar, alledaagse ("betaling", "gent") nauwelijks.

Alles staat versleuteld in de databank en moet dus ontsleuteld worden. Dat
gebeurt één keer; het resultaat blijft in het geheugen tot er iets aan de
bevestigde transacties verandert.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..crypto import normalize

# Meer dan dit wordt niet ingelezen: de recentste transacties zeggen het meest
# over hoe je nu indeelt, en zo blijft het geheugengebruik begrensd.
MAX_TRANSACTIES = 25000

# Woorden die in elke tweede mededeling staan en dus niets onderscheiden. De
# zeldzaamheidsweging vangt de meeste zelf op; deze lijst is voor de korte
# woorden die er toch door zouden glippen.
STOPWOORDEN = {
    "van", "het", "een", "voor", "met", "naar", "bij", "per", "via", "and",
    "the", "des", "les", "pour", "ref", "referentie", "betaling", "factuur",
    "klant", "klantnummer", "nummer", "mededeling", "datum", "bedrag",
}

# Hoe zwaar een woord dat nergens in de historiek staat, meeweegt in de noemer
# van de gelijkenisscore; en hoeveel gewicht de gedeelde woorden samen minstens
# moeten hebben. Een woord dat in 1 op 20 transacties staat, weegt ongeveer 4.
ONBEKEND_GEWICHT = 1.0
MIN_BEWIJS = 3.0

# Waarden die in de gegevens "niets ingevuld" betekenen.
ZONDER_WAARDE = {"-", "--", "?", "n/a", "nvt", "geen", "."}


def woorden(tekst: str) -> set[str]:
    """De onderscheidende woorden van een tekst.

    Naast het woord zelf ook de eerste vijf letters als apart kenmerk (met een
    # ervoor), zodat "boeken" en "boekenreeks" elkaar vinden.
    """
    uit: set[str] = set()
    for woord in normalize(tekst).split():
        if len(woord) < 3 or woord in STOPWOORDEN:
            continue
        cijfers = sum(c.isdigit() for c in woord)
        if cijfers > 2:  # factuur- en klantnummers: uniek, dus ruis
            continue
        uit.add(woord)
        if len(woord) >= 6:
            uit.add("#" + woord[:5])
    return uit


def _schoon(tekst: str | None) -> str:
    tekst = " ".join((tekst or "").split())
    return "" if tekst.lower() in ZONDER_WAARDE else tekst


@dataclass
class Document:
    ids: tuple
    tegenpartij: str
    mededeling: str


@dataclass
class Richting:
    """Alles wat voor één richting (in of uit) geleerd is."""
    telling: Counter = field(default_factory=Counter)             # ids -> aantal
    namen: dict = field(default_factory=lambda: defaultdict(Counter))  # ids -> namen
    documenten: list[Document] = field(default_factory=list)
    index: dict = field(default_factory=lambda: defaultdict(list))  # woord -> [doc]

    def gewicht(self, woord: str) -> float:
        """Hoe zeldzaam een bekend woord is: hoe zeldzamer, hoe zwaarder."""
        n = len(self.documenten) or 1
        df = len(self.index.get(woord, ()))
        basis = math.log((n + 1) / (df + 1)) + 1.0
        return basis * (0.5 if woord.startswith("#") else 1.0)


@dataclass
class Gelijkaardig:
    ids: tuple
    tegenpartij: str
    mededeling: str
    score: float
    richting: str = "uit"


class Historiek:
    def __init__(self):
        self.richtingen: dict[str, Richting] = {"in": Richting(), "uit": Richting()}

    def richting(self, richting: str) -> Richting:
        return self.richtingen.get(richting) or Richting()

    def lijkt_op(self, richting: str, tegenpartij: str, mededeling: str,
                 aantal: int = 6, drempel: float = 0.25) -> list[Gelijkaardig]:
        """De eerdere transacties die het meest op deze lijken.

        Score: het gewicht van de gedeelde woorden, gedeeld door het gewicht
        van alle woorden van de nieuwe transactie. Een woord dat nergens in de
        historiek voorkomt ("jasper", "rokje") telt in die noemer maar licht
        mee: het zegt niets over gelijkenis, en zou anders een sterke treffer
        op een zeldzaam gedeeld woord ("chiro") wegdrukken. Omgekeerd moet het
        gedeelde bewijs op zich stevig genoeg zijn (MIN_BEWIJS), zodat één
        alledaags woord geen treffer oplevert.

        Woorden die in meer dan een op tien transacties staan, tellen niet mee
        om kandidaten te zoeken — die leveren duizenden treffers op en
        onderscheiden niets.
        """
        r = self.richting(richting)
        gevraagd = woorden(f"{tegenpartij} {mededeling}")
        if not gevraagd or not r.documenten:
            return []
        gewichten = {w: r.gewicht(w) for w in gevraagd if w in r.index}
        onbekend = len(gevraagd) - len(gewichten)
        totaal = sum(gewichten.values()) + ONBEKEND_GEWICHT * onbekend
        if not gewichten:
            return []
        grens = max(50, len(r.documenten) // 10)

        scores: dict[int, float] = defaultdict(float)
        for woord, gewicht in gewichten.items():
            treffers = r.index.get(woord, ())
            if len(treffers) > grens:
                continue
            for d in treffers:
                scores[d] += gewicht

        uit: list[Gelijkaardig] = []
        gezien: set = set()
        for d, s in sorted(scores.items(), key=lambda p: -p[1]):
            score = s / totaal
            if score < drempel or s < MIN_BEWIJS:
                break
            doc = r.documenten[d]
            sleutel = (doc.ids, normalize(doc.tegenpartij))
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            uit.append(Gelijkaardig(doc.ids, doc.tegenpartij, doc.mededeling,
                                    round(score, 2), richting))
            if len(uit) >= aantal:
                break
        return uit


_cache: dict = {}


def _stempel(conn) -> tuple:
    rij = conn.execute(
        "SELECT COUNT(*) n, IFNULL(MAX(gewijzigd_op), '') m FROM transacties"
        " WHERE status = 'bevestigd'").fetchone()
    return (rij["n"], rij["m"])


def laad(conn, crypto) -> Historiek:
    """De historiek, uit het geheugen als er sindsdien niets veranderde."""
    stempel = _stempel(conn)
    if _cache.get("stempel") == stempel:
        return _cache["historiek"]

    h = Historiek()
    for rij in conn.execute(
        "SELECT richting, categorie_id, subcategorie_id, subsub_id,"
        " tegenpartij_naam_enc, handelaar_enc, begunstigde_enc, mededeling_enc"
        " FROM transacties WHERE status = 'bevestigd' AND categorie_id IS NOT NULL"
        " AND is_afrekening = 0 ORDER BY boekdatum DESC, id DESC LIMIT ?",
        (MAX_TRANSACTIES,),
    ):
        r = h.richtingen.get(rij["richting"])
        if r is None:
            continue
        ids = (rij["categorie_id"], rij["subcategorie_id"], rij["subsub_id"])
        tegenpartij = (_schoon(crypto.dec(rij["tegenpartij_naam_enc"]))
                       or _schoon(crypto.dec(rij["begunstigde_enc"])))
        handelaar = _schoon(crypto.dec(rij["handelaar_enc"]))
        mededeling = _schoon(crypto.dec(rij["mededeling_enc"]))

        r.telling[ids] += 1
        naam = handelaar or tegenpartij
        if naam:
            r.namen[ids][naam[:30]] += 1

        d = len(r.documenten)
        r.documenten.append(Document(ids, tegenpartij or handelaar, mededeling[:80]))
        for woord in woorden(f"{tegenpartij} {handelaar} {mededeling}"):
            r.index[woord].append(d)

    _cache["stempel"] = stempel
    _cache["historiek"] = h
    return h


def vergeet() -> None:
    _cache.clear()
