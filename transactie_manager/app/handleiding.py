"""De handleiding tonen in de toepassing zelf.

Er zit bewust geen markdownbibliotheek achter. De handleiding is één bestand dat
wij zelf schrijven, in een vaste en beperkte opmaak: koppen, alinea's,
opsommingen, tabellen, citaten, code en links. Daar een afhankelijkheid voor
binnenhalen betekent een pakket meer om te bouwen en te onderhouden in de Home
Assistant add-on, voor een bestand waarvan wij elke regel zelf typen.

Wat hier staat dekt dus precies wat `docs/HANDLEIDING.md` gebruikt, en niet meer.
Komt er ooit opmaak bij die hier niet in staat, dan valt ze terug op gewone
tekst — lelijk, maar leesbaar, en nooit stuk.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import BASE_DIR

HANDLEIDING = BASE_DIR.parent / "docs" / "HANDLEIDING.md"

_VET = re.compile(r"\*\*(.+?)\*\*")
_CURSIEF = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")
_CODE = re.compile(r"`([^`]+?)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_KOP = re.compile(r"^(#{1,4})\s+(.*)$")
_OPSOMMING = re.compile(r"^(\s*)[-*]\s+(.*)$")
_GENUMMERD = re.compile(r"^(\s*)\d+\.\s+(.*)$")
_SCHEIDING = re.compile(r"^---+$")


@dataclass
class Kop:
    """Een kop in de inhoudstafel."""
    niveau: int
    tekst: str
    anker: str


@dataclass
class Handleiding:
    html: str = ""
    koppen: list[Kop] = field(default_factory=list)
    gevonden: bool = True


def lees(pad: Path | None = None) -> Handleiding:
    bestand = pad or HANDLEIDING
    try:
        tekst = bestand.read_text(encoding="utf-8")
    except OSError:
        return Handleiding(gevonden=False)
    return _naar_html(tekst)


def _anker(tekst: str, gebruikt: set[str]) -> str:
    kaal = re.sub(r"[^a-z0-9]+", "-", _kaal(tekst).lower()).strip("-") or "deel"
    anker, n = kaal, 2
    while anker in gebruikt:
        anker, n = f"{kaal}-{n}", n + 1
    gebruikt.add(anker)
    return anker


def _kaal(tekst: str) -> str:
    """De tekst zonder opmaak, voor ankers en de inhoudstafel."""
    tekst = _LINK.sub(r"\1", tekst)
    return tekst.replace("*", "").replace("`", "").strip()


def _inline(tekst: str) -> str:
    """Opmaak binnen een regel. Eerst ontsnappen, dan pas opmaken."""
    uit = html.escape(tekst)
    uit = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", uit)
    uit = _LINK.sub(_link, uit)
    uit = _VET.sub(r"<strong>\1</strong>", uit)
    uit = _CURSIEF.sub(r"<em>\1</em>", uit)
    return uit


def _link(treffer: re.Match) -> str:
    label, doel = treffer.group(1), treffer.group(2)
    if doel.startswith("#"):
        return f'<a href="{doel}">{label}</a>'
    if doel.startswith(("http://", "https://")):
        return f'<a href="{doel}" target="_blank" rel="noopener">{label}</a>'
    # Verwijzingen naar andere bestanden in de repository hebben hier geen doel.
    return label


def _naar_html(tekst: str) -> Handleiding:
    regels = tekst.split("\n")
    uit: list[str] = []
    koppen: list[Kop] = []
    gebruikt: set[str] = set()

    i = 0
    n = len(regels)
    while i < n:
        regel = regels[i]
        kaal = regel.strip()

        if not kaal:
            i += 1
            continue

        if kaal.startswith("```"):
            i += 1
            blok = []
            while i < n and not regels[i].strip().startswith("```"):
                blok.append(html.escape(regels[i]))
                i += 1
            i += 1
            uit.append("<pre><code>" + "\n".join(blok) + "</code></pre>")
            continue

        if _SCHEIDING.match(kaal):
            uit.append("<hr>")
            i += 1
            continue

        treffer = _KOP.match(kaal)
        if treffer:
            niveau = len(treffer.group(1))
            inhoud = treffer.group(2)
            anker = _anker(inhoud, gebruikt)
            if niveau <= 3:
                koppen.append(Kop(niveau, _kaal(inhoud), anker))
            uit.append(f'<h{niveau} id="{anker}">{_inline(inhoud)}</h{niveau}>')
            i += 1
            continue

        # Tabel: een regel met pijpen, gevolgd door een scheidingsregel.
        if "|" in kaal and i + 1 < n and set(regels[i + 1].strip()) <= set("|-: "):
            i, blok = _tabel(regels, i)
            uit.append(blok)
            continue

        if kaal.startswith(">"):
            blok = []
            while i < n and regels[i].strip().startswith(">"):
                blok.append(regels[i].strip().lstrip(">").strip())
                i += 1
            uit.append("<blockquote><p>" + _inline(" ".join(blok)) + "</p></blockquote>")
            continue

        if _OPSOMMING.match(regel) or _GENUMMERD.match(regel):
            i, blok = _lijst(regels, i)
            uit.append(blok)
            continue

        # Gewone alinea: alles tot de volgende lege regel of nieuw blok.
        blok = []
        while i < n and regels[i].strip() and not _nieuw_blok(regels[i]):
            blok.append(regels[i].strip())
            i += 1
        uit.append("<p>" + _inline(" ".join(blok)) + "</p>")

    return Handleiding(html="\n".join(uit), koppen=koppen)


def _nieuw_blok(regel: str) -> bool:
    kaal = regel.strip()
    return bool(
        _KOP.match(kaal) or _SCHEIDING.match(kaal) or kaal.startswith((">", "```"))
        or _OPSOMMING.match(regel) or _GENUMMERD.match(regel) or "|" in kaal
    )


def _lijst(regels: list[str], i: int) -> tuple[int, str]:
    """Eén opsomming, met de nesting die de handleiding gebruikt (één diep)."""
    genummerd = bool(_GENUMMERD.match(regels[i]))
    tag = "ol" if genummerd else "ul"
    stukken = [f"<{tag}>"]
    open_sub = False
    n = len(regels)

    while i < n:
        treffer = _GENUMMERD.match(regels[i]) or _OPSOMMING.match(regels[i])
        if not treffer:
            if regels[i].strip():
                break
            # Eén lege regel binnen een opsomming hoort er nog bij.
            if i + 1 < n and (_GENUMMERD.match(regels[i + 1])
                              or _OPSOMMING.match(regels[i + 1])):
                i += 1
                continue
            break
        diep = len(treffer.group(1)) >= 2
        inhoud = _inline(treffer.group(2))
        if diep and not open_sub:
            stukken.append("<ul>")
            open_sub = True
        elif not diep and open_sub:
            stukken.append("</ul>")
            open_sub = False
        stukken.append(f"<li>{inhoud}</li>")
        i += 1

    if open_sub:
        stukken.append("</ul>")
    stukken.append(f"</{tag}>")
    return i, "".join(stukken)


def _tabel(regels: list[str], i: int) -> tuple[int, str]:
    def cellen(regel: str) -> list[str]:
        kaal = regel.strip().strip("|")
        return [c.strip() for c in kaal.split("|")]

    kop = cellen(regels[i])
    i += 2  # kopregel en scheidingsregel
    stukken = ["<div class=\"tabel-omhulsel\"><table><thead><tr>"]
    stukken += [f"<th>{_inline(c)}</th>" for c in kop]
    stukken.append("</tr></thead><tbody>")

    n = len(regels)
    while i < n and "|" in regels[i] and regels[i].strip():
        stukken.append("<tr>")
        stukken += [f"<td>{_inline(c)}</td>" for c in cellen(regels[i])]
        stukken.append("</tr>")
        i += 1
    stukken.append("</tbody></table></div>")
    return i, "".join(stukken)
