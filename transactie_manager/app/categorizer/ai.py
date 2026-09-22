"""Stap 3: voorstel door een lokaal AI-model.

Er wordt gepraat met een Ollama-server (of een compatibele server met hetzelfde
`/api/chat`-eindpunt). Het model krijgt de transactiegegevens en de lijst met
toegelaten categoriepaden, en moet altijd één pad kiezen; hoe zeker het is,
geeft het apart op. Optioneel wordt eerst een korte opzoeking via de Brave Search API
gedaan om te achterhalen wat voor zaak de tegenpartij is.

Een voorstel uit deze stap komt altijd op status "nazicht": de gebruiker moet
het bevestigen, net zoals bij een fuzzy suggestie. Elke bevraging — vraag,
ruw antwoord en resultaat — wordt in het logboek gezet (versleuteld, net als
de rest van dat logboek), zodat je kan nakijken wat er precies gebeurd is.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..categories import boom, keuzelijst
from ..crypto import normalize
from ..database import instelling, log
from .. import lokaal
from .engine import TransactieKenmerken, Voorstel

TIMEOUT = 60
BRAVE_ZOEK_URL = "https://api.search.brave.com/res/v1/web/search"

# Hoofdcategorieën waarbij een land van bestemming zin heeft. Bij andere
# uitgaven vulde het model soms toch een land in — het land van de winkel —
# en dat hoort niet in het veld "land van bestemming".
LAND_WOORDEN = ("vakantie", "reis")


def _enkel_spatie(tekst: str) -> str:
    """Bankexports vullen namen soms op met spaties ("LedLoket      Denekamp").
    Dat maakt de vraag aan het model en de zoekopdracht er niet beter op."""
    return " ".join((tekst or "").split())


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
    """Haalt een paar zoekresultaten op over de tegenpartij, via de Brave
    Search API. Faalt stil: geen sleutel ingesteld, geen bereikbare server of
    een andere fout levert gewoon geen context op, en de bevraging van het
    AI-model gaat gewoon door zonder die context."""
    if instelling(conn, "ai_zoeken_actief", "0") != "1" or not zoekterm:
        return ""
    sleutel = lokaal.lees(conn, "brave_api_key")
    if not sleutel:
        return ""
    url = BRAVE_ZOEK_URL + "?" + urllib.parse.urlencode({
        "q": _enkel_spatie(zoekterm) + " winkel bedrijf",
        "count": 5,
    })
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "X-Subscription-Token": sleutel,
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return ""

    resultaten = ((data.get("web") or {}).get("results") or [])[:5]
    stukken = []
    for r in resultaten:
        titel = re.sub(r"<[^>]+>", "", r.get("title") or "").strip()
        beschrijving = re.sub(r"<[^>]+>", "", r.get("description") or "").strip()
        regel = " — ".join(deel for deel in (titel, beschrijving) if deel)
        if regel:
            stukken.append(regel)
    return "\n".join(stukken)[:1200]


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
    "Je bent een boekhoudkundige assistent voor een Belgisch huishouden. Je krijgt "
    "één banktransactie en een genummerde lijst met toegelaten categoriepaden.\n"
    "Werkwijze:\n"
    "1. Bepaal eerst wat voor zaak de tegenpartij is en wat er vermoedelijk gekocht "
    "of betaald werd. Gebruik daarvoor de naam, de mededeling, het bedrag en — als "
    "die er is — de informatie van het web.\n"
    "2. Kies daarna het categoriepad uit de lijst dat daar het best bij past. Je "
    "moet ALTIJD precies één pad uit de lijst kiezen, ook als je twijfelt: kies dan "
    "het meest waarschijnlijke en geef een lage zekerheid op. Weigeren of een "
    "nummer buiten de lijst geven is niet toegelaten.\n"
    "3. Neem het nummer én de volledige tekst van het gekozen pad letterlijk over "
    "uit de lijst.\n"
    "Zekerheid: 0.9 of hoger als het pad duidelijk past, rond 0.6 als het "
    "aannemelijk is, 0.3 of lager als het een gok is.\n"
    "Land: alleen invullen (ISO-landcode, bv. FR) bij een uitgave tijdens een "
    "vakantie of reis. Het land waar een winkel of webshop gevestigd is, telt niet; "
    "laat het dan leeg.\n"
    "Antwoord uitsluitend met JSON, zonder uitleg errond, met de velden in deze "
    "volgorde: "
    '{"reden": "<één of twee korte zinnen: wat voor zaak en waarom dit pad>", '
    '"nummer": <getal uit de lijst>, "pad": "<de tekst van dat pad, letterlijk>", '
    '"handelaar": "<naam van de zaak of leeg>", '
    '"land": "<landcode of leeg>", "zekerheid": <0.0 tot 1.0>}'
)


def _kies_pad(data: dict, paden: list[tuple[str, tuple]]) -> tuple[int, str]:
    """Welk pad heeft het model gekozen?

    Het model geeft zowel een nummer als de tekst van het pad. Bij een lange
    lijst verspringt een klein model al eens een nummer, terwijl de tekst wel
    klopt; de tekst gaat daarom voor als ze letterlijk (op hoofdletters en
    spaties na) in de lijst staat. Geeft (index, hoe gevonden) terug, of
    (-1, "") als geen van beide bruikbaar is.
    """
    def plat(tekst: str) -> str:
        return normalize(re.sub(r"\s*[>›]\s*", " > ", str(tekst or "")))

    gevraagd = plat(data.get("pad", ""))
    if gevraagd:
        for i, (label, _) in enumerate(paden):
            if plat(label) == gevraagd:
                return i, "pad"
    try:
        index = int(data.get("nummer", 0)) - 1
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(paden):
        return index, "nummer"
    return -1, ""


def _log_bevraging(conn, crypto, gebruiker: str | None, model: str,
                    k: TransactieKenmerken, vraag: str, ruw_antwoord: str,
                    voorstel: Voorstel | None, fout: str | None = None) -> None:
    """Zet de volledige bevraging in het logboek: wat er verstuurd werd, wat er
    terugkwam, en wat daaruit volgde. Net als de rest van het logboek wordt dit
    versleuteld opgeslagen."""
    if not gebruiker:
        return
    naam = k.tegenpartij_naam or k.beschrijving or "onbekend"
    stukken = [
        f"Tegenpartij: {naam}",
        f"Bedrag: {abs(k.bedrag)} EUR ({'inkomst' if k.richting == 'in' else 'uitgave'})",
        f"Model: {model}",
        "",
        "Verzonden vraag (systeeminstructie + gebruikersbericht):",
        SYSTEEM,
        "---",
        vraag.strip(),
        "",
        "Ruw antwoord van het model:",
        (ruw_antwoord or "(geen antwoord ontvangen)").strip(),
    ]
    if voorstel is not None:
        stukken += [
            "",
            f"Resultaat: Voorstel: {voorstel.toelichting} "
            f"({round(voorstel.zekerheid * 100)}% zeker).",
        ]
    if fout:
        stukken += ["", f"Resultaat: geen voorstel — {fout}"]
    log(conn, crypto, gebruiker, "ai_bevraagd", "\n".join(stukken))


def stel_voor(conn, crypto, k: TransactieKenmerken, gebruiker: str | None = None) -> Voorstel:
    """Vraagt het model om een voorstel.

    Met `gebruiker` wordt de volledige bevraging — vraag, ruw antwoord en
    resultaat — in het logboek gezet, ook als het model geen bruikbaar
    antwoord geeft. Zonder `gebruiker` (bijvoorbeeld bij een automatische
    aanroep zonder ingelogde context) gebeurt dat niet.
    """
    if not beschikbaar(conn):
        raise AIFout("Het AI-model staat uitgeschakeld in de instellingen.")

    paden = _paden(conn, crypto, k.richting)
    if not paden:
        raise AIFout("Er zijn nog geen categorieën ingesteld.")

    lijst = "\n".join(f"{i + 1}. {label}" for i, (label, _) in enumerate(paden))
    tegenpartij = _enkel_spatie(k.tegenpartij_naam)
    context = _webcontext(conn, tegenpartij)

    vraag = (
        f"Transactie\n"
        f"- Richting: {'inkomst' if k.richting == 'in' else 'uitgave'}\n"
        f"- Bedrag: {abs(k.bedrag)} EUR\n"
        f"- Tegenpartij: {tegenpartij or 'onbekend'}\n"
        f"- Rekening tegenpartij: {k.tegenpartij_rekening or 'onbekend'}\n"
        f"- Mededeling: {_enkel_spatie(k.mededeling) or 'geen'}\n"
    )
    if k.beschrijving:
        vraag += f"- Soort verrichting: {_enkel_spatie(k.beschrijving)}\n"
    if context:
        vraag += f"\nGevonden op het web over de tegenpartij:\n{context}\n"
    vraag += f"\nToegelaten categorieën:\n{lijst}\n"

    basis = instelling(conn, "ai_basis_url").rstrip("/")
    model = instelling(conn, "ai_model")

    inhoud = ""
    try:
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

        index, _ = _kies_pad(data, paden)
        if index < 0:
            raise AIFout("Het model koos geen categorie uit de lijst.")

        label, ids = paden[index]
        zekerheid = data.get("zekerheid", 0.6)
        try:
            zekerheid = max(0.0, min(1.0, float(zekerheid)))
        except (TypeError, ValueError):
            zekerheid = 0.6

        reden = str(data.get("reden", "")).strip()
        handelaar = _enkel_spatie(str(data.get("handelaar", ""))) or None
        land = str(data.get("land", "")).strip() or None
        if land and not any(w in label.lower() for w in LAND_WOORDEN):
            land = None
        if zekerheid < 0.5:
            reden = ("Het model twijfelt. " + reden).strip()

        voorstel = Voorstel(
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
    except AIFout as exc:
        _log_bevraging(conn, crypto, gebruiker, model, k, vraag, inhoud, None, fout=str(exc))
        raise

    _log_bevraging(conn, crypto, gebruiker, model, k, vraag, inhoud, voorstel)
    return voorstel


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
