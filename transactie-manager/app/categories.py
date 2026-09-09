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
        )
    return result


def bouw_boom(platte: dict[int, Categorie]) -> list[Categorie]:
    """Koppelt kinderen aan hun ouder en geeft de wortels terug."""
    for cat in platte.values():
        cat.kinderen = []
    wortels: list[Categorie] = []
    for cat in platte.values():
        if cat.ouder_id and cat.ouder_id in platte:
            platte[cat.ouder_id].kinderen.append(cat)
        elif cat.niveau == 0:
            wortels.append(cat)
    sleutel = lambda c: (c.volgorde, c.naam.lower())  # noqa: E731
    wortels.sort(key=sleutel)
    for cat in platte.values():
        cat.kinderen.sort(key=sleutel)
    return wortels


def boom(conn, crypto, soort: str | None = None, alleen_actief: bool = False) -> list[Categorie]:
    platte = laad_alles(conn, crypto, alleen_actief)
    wortels = bouw_boom(platte)
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
