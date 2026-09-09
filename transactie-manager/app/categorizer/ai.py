"""Stap 3: voorstel door een lokaal AI-model.

Er wordt gepraat met een Ollama-server (of een compatibele server met hetzelfde
`/api/chat`-eindpunt). Het model krijgt de transactiegegevens en de lijst met
toegelaten categoriepaden, en moet één pad kiezen. Optioneel wordt eerst een
korte webopzoeking gedaan om te achterhalen wat voor zaak de tegenpartij is.

Een voorstel uit deze stap komt altijd op status "nazicht": de gebruiker moet
het bevestigen, net zoals bij een fuzzy suggestie.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..categories import boom, keuzelijst
from ..crypto import normalize
from ..database import instelling
from .engine import TransactieKenmerken, Voorstel

TIMEOUT = 60


class AIFout(RuntimeError):
    pass


def beschikbaar(conn) -> bool:
    return instelling(conn, "ai_actief", "0") == "1"


def _http_json(url: str, payload: dict, timeout: int = TIMEOUT) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise AIFout(f"Kon het AI-model niet bereiken: {exc}") from exc


def test_verbinding(conn) -> tuple[bool, str]:
    basis = instelling(conn, "ai_basis_url").rstrip("/")
    try:
        with urllib.request.urlopen(f"{basis}/api/tags", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        modellen = [m.get("name", "") for m in data.get("models", [])]
        if not modellen:
            return True, "Verbinding gelukt, maar er staan nog geen modellen klaar."
        return True, "Verbinding gelukt. Beschikbaar: " + ", ".join(modellen[:8])
    except Exception as exc:  # noqa: BLE001
        return False, f"Geen verbinding: {exc}"


def _webcontext(conn, zoekterm: str) -> str:
    """Haalt een paar regels tekst op over de tegenpartij. Faalt stil."""
    if instelling(conn, "ai_zoeken_actief", "0") != "1" or not zoekterm:
        return ""
    url = instelling(conn, "ai_zoek_url") + urllib.parse.quote_plus(zoekterm + " winkel bedrijf")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "transactie-manager/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read(200_000).decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""
    tekst = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    tekst = re.sub(r"<[^>]+>", " ", tekst)
    tekst = re.sub(r"\s+", " ", tekst)
    return tekst[:1200]


def _paden(conn, crypto, richting: str) -> list[tuple[str, tuple]]:
    """Alle toegelaten categoriepaden als (leesbaar pad, id-tupel)."""
    wortels = boom(conn, crypto, soort=richting, alleen_actief=True)
    resultaat: list[tuple[str, tuple]] = []
    for hoofd in wortels:
        if not hoofd.kinderen:
            resultaat.append((hoofd.naam, (hoofd.id, None, None)))
        for sub in hoofd.kinderen:
            if not sub.kinderen:
                resultaat.append((f"{hoofd.naam} > {sub.naam}", (hoofd.id, sub.id, None)))
            for subsub in sub.kinderen:
                resultaat.append((
                    f"{hoofd.naam} > {sub.naam} > {subsub.naam}",
                    (hoofd.id, sub.id, subsub.id),
                ))
    return resultaat


SYSTEEM = (
    "Je bent een boekhoudkundige assistent. Je krijgt één banktransactie en een "
    "genummerde lijst met toegelaten categoriepaden. Kies het pad dat het best past. "
    "Antwoord uitsluitend met JSON, zonder uitleg errond, in de vorm: "
    '{"nummer": <getal>, "handelaar": "<naam van de zaak of leeg>", '
    '"land": "<landcode bij vakantie-uitgave, anders leeg>", '
    '"zekerheid": <0.0 tot 1.0>, "reden": "<één korte zin>"}'
)


def stel_voor(conn, crypto, k: TransactieKenmerken) -> Voorstel:
    if not beschikbaar(conn):
        raise AIFout("Het AI-model staat uitgeschakeld in de instellingen.")

    paden = _paden(conn, crypto, k.richting)
    if not paden:
        raise AIFout("Er zijn nog geen categorieën ingesteld.")

    lijst = "\n".join(f"{i + 1}. {label}" for i, (label, _) in enumerate(paden))
    context = _webcontext(conn, k.tegenpartij_naam)

    vraag = (
        f"Transactie\n"
        f"- Richting: {'inkomst' if k.richting == 'in' else 'uitgave'}\n"
        f"- Bedrag: {abs(k.bedrag)} EUR\n"
        f"- Tegenpartij: {k.tegenpartij_naam or 'onbekend'}\n"
        f"- Rekening tegenpartij: {k.tegenpartij_rekening or 'onbekend'}\n"
        f"- Mededeling: {k.mededeling or 'geen'}\n"
    )
    if context:
        vraag += f"\nGevonden op het web over de tegenpartij:\n{context}\n"
    vraag += f"\nToegelaten categorieën:\n{lijst}\n"

    basis = instelling(conn, "ai_basis_url").rstrip("/")
    model = instelling(conn, "ai_model")
    antwoord = _http_json(f"{basis}/api/chat", {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": SYSTEEM},
            {"role": "user", "content": vraag},
        ],
    })

    inhoud = (antwoord.get("message") or {}).get("content", "")
    try:
        data = json.loads(inhoud)
    except json.JSONDecodeError:
        gevonden = re.search(r"\{.*\}", inhoud, re.S)
        if not gevonden:
            raise AIFout("Het model gaf geen bruikbaar antwoord.")
        data = json.loads(gevonden.group(0))

    try:
        index = int(data.get("nummer", 0)) - 1
    except (TypeError, ValueError):
        index = -1
    if not 0 <= index < len(paden):
        raise AIFout("Het model koos geen geldige categorie.")

    label, ids = paden[index]
    zekerheid = data.get("zekerheid", 0.6)
    try:
        zekerheid = max(0.0, min(1.0, float(zekerheid)))
    except (TypeError, ValueError):
        zekerheid = 0.6

    reden = str(data.get("reden", "")).strip()
    handelaar = str(data.get("handelaar", "")).strip() or None
    land = str(data.get("land", "")).strip() or None

    return Voorstel(
        categorie_id=ids[0],
        subcategorie_id=ids[1],
        subsub_id=ids[2],
        handelaar=handelaar,
        land=land,
        zekerheid=round(zekerheid, 3),
        methode="ai",
        status="nazicht",
        toelichting=f"Voorstel van {model}: {label}." + (f" {reden}" if reden else ""),
    )


def maak_regel_van_voorstel(conn, crypto, k: TransactieKenmerken, voorstel: Voorstel) -> None:
    """Legt een bevestigd AI- of fuzzy-voorstel vast als vaste regel."""
    from ..database import now_iso

    waarde = (voorstel.handelaar or k.tegenpartij_naam or "").strip()
    if not waarde:
        return
    bestaand = conn.execute(
        "SELECT id FROM regels WHERE waarde_idx = ? AND veld='tegenpartij_naam'"
        " AND IFNULL(categorie_id,0)=IFNULL(?,0) AND IFNULL(subcategorie_id,0)=IFNULL(?,0)",
        (crypto.blind(waarde), voorstel.categorie_id, voorstel.subcategorie_id),
    ).fetchone()
    if bestaand:
        return
    conn.execute(
        "INSERT INTO regels (naam_enc, prioriteit, veld, operator, waarde_enc, waarde_idx,"
        " richting, categorie_id, subcategorie_id, subsub_id, handelaar_enc, land_enc,"
        " aangemaakt_op) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            crypto.enc(f"Geleerd van {waarde}"), 50, "tegenpartij_naam", "bevat",
            crypto.enc(normalize(waarde)), crypto.blind(normalize(waarde)),
            k.richting, voorstel.categorie_id, voorstel.subcategorie_id, voorstel.subsub_id,
            crypto.enc(voorstel.handelaar) if voorstel.handelaar else None,
            crypto.enc(voorstel.land) if voorstel.land else None,
            now_iso(),
        ),
    )
