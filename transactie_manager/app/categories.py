"""Hulpfuncties rond de categorieboom.

Categorienamen staan versleuteld in de databank. De boom is klein (enkele
honderden rijen), dus die wordt per aanvraag volledig ontsleuteld en in het
geheugen opgebouwd.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .crypto import normalize


@dataclass
class Categorie:
    id: int
    ouder_id: int | None
    niveau: int
    soort: str
    naam: str
    volgorde: int
    actief: bool
    kinderen: list["Categorie"] = field(default_factory=list)
    # Wat jij onder deze categorie verstaat, in trefwoorden. Gaat mee naar het
    # AI-model.
    omschrijving: str = ""

    @property
    def naam_genormaliseerd(self) -> str:
        return normalize(self.naam)


def laad_alles(conn, crypto, alleen_actief: bool = False) -> dict[int, Categorie]:
    sql = "SELECT * FROM categorieen"
    if alleen_actief:
        sql += " WHERE actief = 1"
    sql += " ORDER BY niveau, volgorde, id"
    result: dict[int, Categorie] = {}
    for row in conn.execute(sql):
        result[row["id"]] = Categorie(
            id=row["id"],
            ouder_id=row["ouder_id"],
            niveau=row["niveau"],
            soort=row["soort"],
            naam=crypto.dec(row["naam_enc"]) or "",
            volgorde=row["volgorde"],
            actief=bool(row["actief"]),
            omschrijving=(crypto.dec(row["omschrijving_enc"]) or ""
                          if "omschrijving_enc" in row.keys() else ""),
        )
    return result


def bouw_boom(platte: dict[int, Categorie], alfabetisch: bool = False) -> list[Categorie]:
    """Koppelt kinderen aan hun ouder en geeft de wortels terug.

    `alfabetisch` negeert de handmatige volgorde. In een filterlijst zoek je op
    naam en wil je alfabetisch; op het scherm waar je de boom beheert telt de
    volgorde die je zelf hebt ingesteld.
    """
    for cat in platte.values():
        cat.kinderen = []
    wortels: list[Categorie] = []
    for cat in platte.values():
        if cat.ouder_id and cat.ouder_id in platte:
            platte[cat.ouder_id].kinderen.append(cat)
        elif cat.niveau == 0:
            wortels.append(cat)
    if alfabetisch:
        def sleutel(c):
            return (c.naam.lower(),)
    else:
        def sleutel(c):
            return (c.volgorde, c.naam.lower())
    wortels.sort(key=sleutel)
    for cat in platte.values():
        cat.kinderen.sort(key=sleutel)
    return wortels


def boom(conn, crypto, soort: str | None = None, alleen_actief: bool = False,
         alfabetisch: bool = False) -> list[Categorie]:
    platte = laad_alles(conn, crypto, alleen_actief)
    wortels = bouw_boom(platte, alfabetisch)
    if soort in ("in", "uit"):
        wortels = [c for c in wortels if c.soort in (soort, "beide")]
    return wortels


def pad_namen(platte: dict[int, Categorie], *ids) -> list[str]:
    return [platte[i].naam for i in ids if i and i in platte]


def pad_tekst(platte: dict[int, Categorie], *ids, scheiding: str = " › ") -> str:
    namen = pad_namen(platte, *ids)
    return scheiding.join(namen) if namen else "—"


def zoek_pad(conn, crypto, hoofd: str, sub: str | None = None, subsub: str | None = None):
    """Zoekt (hoofd, sub, subsub) op naam. Geeft een tupel van id's of None."""
    platte = laad_alles(conn, crypto)
    doel = normalize(hoofd)
    hoofd_cat = next(
        (c for c in platte.values() if c.niveau == 0 and c.naam_genormaliseerd == doel), None
    )
    if hoofd_cat is None:
        return None
    sub_id = subsub_id = None
    if sub:
        doel = normalize(sub)
        sub_cat = next(
            (c for c in platte.values()
             if c.ouder_id == hoofd_cat.id and c.naam_genormaliseerd == doel),
            None,
        )
        if sub_cat is None:
            return None
        sub_id = sub_cat.id
        if subsub:
            doel = normalize(subsub)
            ss = next(
                (c for c in platte.values()
                 if c.ouder_id == sub_id and c.naam_genormaliseerd == doel),
                None,
            )
            if ss is None:
                return (hoofd_cat.id, sub_id, None)
            subsub_id = ss.id
    return (hoofd_cat.id, sub_id, subsub_id)


def keuzelijst(wortels: list[Categorie]) -> list[dict]:
    """Platte lijst met inspringing, bruikbaar in een <select>."""
    out: list[dict] = []

    def loop(cat: Categorie, diepte: int):
        out.append({
            "id": cat.id,
            "naam": cat.naam,
            "niveau": cat.niveau,
            "soort": cat.soort,
            "label": ("\u00a0" * 4 * diepte) + cat.naam,
            "ouder_id": cat.ouder_id,
            "omschrijving": cat.omschrijving,
        })
        for kind in cat.kinderen:
            loop(kind, diepte + 1)

    for wortel in wortels:
        loop(wortel, 0)
    return out


def nakomelingen(platte: dict[int, Categorie], cat_id: int) -> set[int]:
    """Alle id's onder een categorie, inclusief zichzelf."""
    resultaat = {cat_id}
    te_doen = [cat_id]
    kinderen_van: dict[int, list[int]] = {}
    for cat in platte.values():
        if cat.ouder_id:
            kinderen_van.setdefault(cat.ouder_id, []).append(cat.id)
    while te_doen:
        huidig = te_doen.pop()
        for kind in kinderen_van.get(huidig, []):
            if kind not in resultaat:
                resultaat.add(kind)
                te_doen.append(kind)
    return resultaat


def zoek_of_maak(conn, crypto, hoofd: str, sub: str = "", subsub: str = "",
                 soort: str = "beide", cache: dict | None = None) -> tuple:
    """Zoekt het pad (hoofd, sub, subsub) op naam en maakt aan wat ontbreekt.

    Geeft een tupel met drie id's terug; ontbrekende niveaus worden None. De
    vergelijking is hoofdletterongevoelig, zodat "Auto" en "auto" dezelfde
    categorie blijven. Geef een woordenboek mee als `cache` om bij een grote
    invoer niet per rij opnieuw te hoeven opzoeken.
    """
    if cache is None:
        cache = {}
    if "_geladen" not in cache:
        cache["_geladen"] = True
        cache["_paden"] = {}
        for row in conn.execute("SELECT id, ouder_id, naam_enc FROM categorieen"):
            cache["_paden"][(row["ouder_id"], normalize(crypto.dec(row["naam_enc"])))] = row["id"]

    paden = cache["_paden"]

    def niveau(naam: str, diepte: int, ouder_id):
        genormaliseerd = normalize(naam)
        if not genormaliseerd:
            return None
        sleutel = (ouder_id, genormaliseerd)
        if sleutel in paden:
            return paden[sleutel]
        volgorde = conn.execute(
            "SELECT COUNT(*) n FROM categorieen WHERE IFNULL(ouder_id,0)=?",
            (ouder_id or 0,)).fetchone()["n"]
        cur = conn.execute(
            "INSERT INTO categorieen (ouder_id, niveau, soort, naam_enc, naam_idx, volgorde)"
            " VALUES (?,?,?,?,?,?)",
            (ouder_id, diepte, soort, crypto.enc(naam.strip()), crypto.blind(naam), volgorde),
        )
        paden[sleutel] = cur.lastrowid
        return cur.lastrowid

    hid = niveau(hoofd, 0, None)
    if hid is None:
        return (None, None, None)
    sid = niveau(sub, 1, hid)
    ssid = niveau(subsub, 2, sid) if sid else None
    return (hid, sid, ssid)
