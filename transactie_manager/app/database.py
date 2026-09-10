"""SQLite-laag: verbinding, schema en beginwaarden."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from flask import g

from .config import DB_PATH, DEFAULT_SETTINGS

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta (
    sleutel TEXT PRIMARY KEY,
    waarde  TEXT
);

CREATE TABLE IF NOT EXISTS gebruikers (
    id            INTEGER PRIMARY KEY,
    gebruikersnaam TEXT NOT NULL UNIQUE,
    pw_salt       BLOB NOT NULL,
    pw_verif      TEXT NOT NULL,
    dek_wrapped   TEXT NOT NULL,
    is_beheerder  INTEGER NOT NULL DEFAULT 0,
    actief        INTEGER NOT NULL DEFAULT 1,
    aangemaakt_op TEXT NOT NULL,
    laatste_login TEXT
);

CREATE TABLE IF NOT EXISTS instellingen (
    sleutel TEXT PRIMARY KEY,
    waarde  TEXT
);

CREATE TABLE IF NOT EXISTS rekeningen (
    id           INTEGER PRIMARY KEY,
    naam_enc     TEXT NOT NULL,
    iban_enc     TEXT,
    iban_idx     TEXT,
    bank_enc     TEXT,
    munt         TEXT NOT NULL DEFAULT 'EUR',
    actief       INTEGER NOT NULL DEFAULT 1,
    volgorde     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_rek_iban ON rekeningen(iban_idx);

CREATE TABLE IF NOT EXISTS categorieen (
    id        INTEGER PRIMARY KEY,
    ouder_id  INTEGER REFERENCES categorieen(id) ON DELETE CASCADE,
    niveau    INTEGER NOT NULL,            -- 0 = hoofd, 1 = sub, 2 = sub-sub
    soort     TEXT NOT NULL DEFAULT 'uit', -- 'in' | 'uit' | 'beide'
    naam_enc  TEXT NOT NULL,
    naam_idx  TEXT,
    volgorde  INTEGER NOT NULL DEFAULT 0,
    actief    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_cat_ouder ON categorieen(ouder_id);

CREATE TABLE IF NOT EXISTS regels (
    id            INTEGER PRIMARY KEY,
    naam_enc      TEXT,
    prioriteit    INTEGER NOT NULL DEFAULT 100,
    veld          TEXT NOT NULL,   -- tegenpartij_naam | tegenpartij_rekening | mededeling
                                   -- | beschrijving | sleutel | alles
    operator      TEXT NOT NULL,   -- gelijk | bevat | regex
    waarde_enc    TEXT NOT NULL,
    waarde_idx    TEXT,
    bedrag_min    REAL,
    bedrag_max    REAL,
    richting      TEXT,            -- in | uit | NULL (beide)
    categorie_id     INTEGER REFERENCES categorieen(id) ON DELETE SET NULL,
    subcategorie_id  INTEGER REFERENCES categorieen(id) ON DELETE SET NULL,
    subsub_id        INTEGER REFERENCES categorieen(id) ON DELETE SET NULL,
    handelaar_enc TEXT,
    land_enc      TEXT,
    actief        INTEGER NOT NULL DEFAULT 1,
    treffers      INTEGER NOT NULL DEFAULT 0,
    herkomst      TEXT NOT NULL DEFAULT 'handmatig',
    aangemaakt_op TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_regel_idx ON regels(waarde_idx);

CREATE TABLE IF NOT EXISTS import_batches (
    id            INTEGER PRIMARY KEY,
    bestand_enc   TEXT,
    profiel       TEXT,
    aantal_rijen  INTEGER NOT NULL DEFAULT 0,
    aantal_nieuw  INTEGER NOT NULL DEFAULT 0,
    aantal_dubbel INTEGER NOT NULL DEFAULT 0,
    gebruiker     TEXT,
    tijdstip      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transacties (
    id                       INTEGER PRIMARY KEY,
    rekening_id              INTEGER NOT NULL REFERENCES rekeningen(id),
    boekdatum                TEXT NOT NULL,
    valutadatum              TEXT,
    verrichtingsdatum        TEXT,
    referentie_enc           TEXT,
    beschrijving_enc         TEXT,
    beschrijving_idx         TEXT,
    sleutel_idx              TEXT,
    richting                 TEXT NOT NULL,          -- 'in' | 'uit'
    bedrag_enc               TEXT NOT NULL,
    munt                     TEXT NOT NULL DEFAULT 'EUR',
    tegenpartij_naam_enc     TEXT,
    tegenpartij_naam_idx     TEXT,
    tegenpartij_rek_enc      TEXT,
    tegenpartij_rek_idx      TEXT,
    begunstigde_enc          TEXT,
    mededeling_enc           TEXT,
    handelaar_enc            TEXT,
    handelaar_idx            TEXT,
    land_enc                 TEXT,
    categorie_id             INTEGER REFERENCES categorieen(id) ON DELETE SET NULL,
    subcategorie_id          INTEGER REFERENCES categorieen(id) ON DELETE SET NULL,
    subsub_id                INTEGER REFERENCES categorieen(id) ON DELETE SET NULL,
    zekerheid                REAL NOT NULL DEFAULT 0,
    methode                  TEXT NOT NULL DEFAULT 'geen',  -- regel|fuzzy|ai|manueel|geen
    status                   TEXT NOT NULL DEFAULT 'nazicht', -- bevestigd|nazicht|niet_toegewezen
    toelichting_enc          TEXT,
    vingerafdruk             TEXT UNIQUE,
    batch_id                 INTEGER REFERENCES import_batches(id) ON DELETE SET NULL,
    ruwe_data_enc            TEXT,
    is_afrekening            INTEGER NOT NULL DEFAULT 0,
    ouder_tx_id              INTEGER REFERENCES transacties(id) ON DELETE CASCADE,
    bron                     TEXT NOT NULL DEFAULT 'bank',
    aangemaakt_op            TEXT NOT NULL,
    gewijzigd_op             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tx_datum   ON transacties(boekdatum);
CREATE INDEX IF NOT EXISTS ix_tx_status  ON transacties(status);
CREATE INDEX IF NOT EXISTS ix_tx_cat     ON transacties(categorie_id);
CREATE INDEX IF NOT EXISTS ix_tx_rek     ON transacties(rekening_id);
CREATE INDEX IF NOT EXISTS ix_tx_tpnaam  ON transacties(tegenpartij_naam_idx);
CREATE INDEX IF NOT EXISTS ix_tx_sleutel ON transacties(sleutel_idx);
CREATE INDEX IF NOT EXISTS ix_tx_ouder   ON transacties(ouder_tx_id);

CREATE TABLE IF NOT EXISTS logboek (
    id        INTEGER PRIMARY KEY,
    tijdstip  TEXT NOT NULL,
    gebruiker TEXT,
    actie     TEXT NOT NULL,
    detail_enc TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT waarde FROM app_meta WHERE sleutel='schema_versie'")
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_meta (sleutel, waarde) VALUES ('schema_versie', ?)",
                (str(SCHEMA_VERSION),),
            )
        for sleutel, waarde in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO instellingen (sleutel, waarde) VALUES (?, ?)",
                (sleutel, waarde),
            )
        conn.commit()
    finally:
        conn.close()


def heeft_gebruikers() -> bool:
    conn = connect()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM gebruikers").fetchone()["n"] > 0
    finally:
        conn.close()


def instelling(conn: sqlite3.Connection, sleutel: str, standaard: str = "") -> str:
    row = conn.execute(
        "SELECT waarde FROM instellingen WHERE sleutel = ?", (sleutel,)
    ).fetchone()
    if row is None:
        return DEFAULT_SETTINGS.get(sleutel, standaard)
    return row["waarde"]


def zet_instelling(conn: sqlite3.Connection, sleutel: str, waarde: str) -> None:
    conn.execute(
        "INSERT INTO instellingen (sleutel, waarde) VALUES (?, ?) "
        "ON CONFLICT(sleutel) DO UPDATE SET waarde = excluded.waarde",
        (sleutel, str(waarde)),
    )


def log(conn: sqlite3.Connection, crypto, gebruiker: str, actie: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO logboek (tijdstip, gebruiker, actie, detail_enc) VALUES (?,?,?,?)",
        (now_iso(), gebruiker, actie, crypto.enc(detail) if detail else None),
    )


# --------------------------------------------------------------------------
# Beginwaarden: categorieboom en enkele voorbeeldregels
# --------------------------------------------------------------------------

STANDAARD_CATEGORIEEN = {
    "uit": {
        "Wonen": {
            "Huur en lening": ["Huur", "Hypothecaire lening", "Syndic"],
            "Nutsvoorzieningen": ["Elektriciteit", "Gas", "Water", "Internet en telefonie"],
            "Onderhoud": ["Herstellingen", "Tuin", "Meubels en inrichting"],
            "Verzekeringen woning": ["Brandverzekering", "Schuldsaldo"],
        },
        "Boodschappen": {
            "Supermarkt": ["Groot inkopen", "Dagelijkse aankopen"],
            "Speciaalzaak": ["Bakker", "Slager", "Markt"],
            "Drank": ["Slijterij", "Frisdrank"],
        },
        "Vervoer": {
            "Auto": ["Tanken", "Onderhoud en herstelling", "Verzekering", "Belasting", "Parkeren"],
            "Openbaar vervoer": ["Trein", "Bus en tram", "Deelmobiliteit"],
            "Fiets": ["Aankoop", "Onderhoud"],
        },
        "Vrije tijd": {
            "Restaurant en café": ["Restaurant", "Café", "Afhaal en levering"],
            "Cultuur": ["Bioscoop", "Concert", "Museum", "Boeken"],
            "Sport": ["Abonnement", "Uitrusting"],
            "Abonnementen": ["Streaming", "Kranten en tijdschriften"],
        },
        "Vakantie": {
            "Verblijf": ["Hotel", "Huurwoning", "Camping"],
            "Reis": ["Vliegtuig", "Trein", "Huurauto", "Brandstof buitenland"],
            "Ter plaatse": ["Eten en drinken", "Uitstappen", "Souvenirs"],
        },
        "Gezondheid": {
            "Zorg": ["Huisarts", "Specialist", "Tandarts", "Kinesitherapie"],
            "Apotheek": ["Voorschrift", "Vrije verkoop"],
            "Verzekering": ["Mutualiteit", "Hospitalisatie"],
        },
        "Gezin": {
            "Kinderen": ["School", "Opvang", "Kleding", "Speelgoed"],
            "Huisdieren": ["Voeding", "Dierenarts"],
            "Kleding": ["Volwassenen", "Schoenen"],
        },
        "Financieel": {
            "Bankkosten": ["Beheerskosten", "Kaartkosten", "Intresten"],
            "Belastingen": ["Personenbelasting", "Gemeentebelasting", "Onroerende voorheffing"],
            "Sparen en beleggen": ["Spaarrekening", "Beleggingen", "Pensioensparen"],
        },
        "Overig": {
            "Giften": ["Goede doelen", "Cadeaus"],
            "Onbekend": ["Nog te bepalen"],
        },
    },
    "in": {
        "Inkomen": {
            "Loon": ["Nettoloon", "Vakantiegeld", "Eindejaarspremie"],
            "Zelfstandige": ["Facturen", "Voorschotten"],
            "Uitkering": ["Werkloosheid", "Ziekte", "Pensioen"],
        },
        "Toelagen": {
            "Kinderbijslag": ["Groeipakket"],
            "Terugbetalingen": ["Mutualiteit", "Verzekering", "Belastingen"],
        },
        "Overige inkomsten": {
            "Verkoop": ["Tweedehands"],
            "Opbrengsten": ["Intresten", "Dividenden", "Huurinkomsten"],
        },
    },
}


def seed_categorieen(conn: sqlite3.Connection, crypto) -> None:
    """Vult de categorieboom als die nog leeg is."""
    if conn.execute("SELECT COUNT(*) AS n FROM categorieen").fetchone()["n"] > 0:
        return

    def voeg_toe(naam, niveau, soort, ouder_id, volgorde):
        cur = conn.execute(
            "INSERT INTO categorieen (ouder_id, niveau, soort, naam_enc, naam_idx, volgorde) "
            "VALUES (?,?,?,?,?,?)",
            (ouder_id, niveau, soort, crypto.enc(naam), crypto.blind(naam), volgorde),
        )
        return cur.lastrowid

    for soort, hoofdcats in STANDAARD_CATEGORIEEN.items():
        for i, (hoofd, subs) in enumerate(hoofdcats.items()):
            hid = voeg_toe(hoofd, 0, soort, None, i)
            for j, (sub, subsubs) in enumerate(subs.items()):
                sid = voeg_toe(sub, 1, soort, hid, j)
                for k, subsub in enumerate(subsubs):
                    voeg_toe(subsub, 2, soort, sid, k)


def seed_voorbeeldregels(conn: sqlite3.Connection, crypto) -> None:
    """Twee regels die het bedragafhankelijke gedrag tonen (Total-voorbeeld)."""
    if conn.execute("SELECT COUNT(*) AS n FROM regels").fetchone()["n"] > 0:
        return

    from .categories import zoek_pad

    voorbeelden = [
        {
            "naam": "Total onder 10 euro is winkelaankoop",
            "prioriteit": 10,
            "veld": "tegenpartij_naam",
            "operator": "bevat",
            "waarde": "total",
            "bedrag_min": None,
            "bedrag_max": 10.0,
            "richting": "uit",
            "pad": ("Boodschappen", "Speciaalzaak", "Dagelijkse aankopen"),
            "pad_fallback": ("Boodschappen", "Supermarkt", "Dagelijkse aankopen"),
            "handelaar": "Total",
        },
        {
            "naam": "Total vanaf 10 euro is tanken",
            "prioriteit": 11,
            "veld": "tegenpartij_naam",
            "operator": "bevat",
            "waarde": "total",
            "bedrag_min": 10.0,
            "bedrag_max": None,
            "richting": "uit",
            "pad": ("Vervoer", "Auto", "Tanken"),
            "pad_fallback": None,
            "handelaar": "Total",
        },
    ]

    for v in voorbeelden:
        ids = zoek_pad(conn, crypto, *v["pad"])
        if ids is None and v["pad_fallback"]:
            ids = zoek_pad(conn, crypto, *v["pad_fallback"])
        if ids is None:
            continue
        conn.execute(
            "INSERT INTO regels (naam_enc, prioriteit, veld, operator, waarde_enc, waarde_idx,"
            " bedrag_min, bedrag_max, richting, categorie_id, subcategorie_id, subsub_id,"
            " handelaar_enc, aangemaakt_op) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                crypto.enc(v["naam"]), v["prioriteit"], v["veld"], v["operator"],
                crypto.enc(v["waarde"]), crypto.blind(v["waarde"]),
                v["bedrag_min"], v["bedrag_max"], v["richting"],
                ids[0], ids[1], ids[2],
                crypto.enc(v["handelaar"]), now_iso(),
            ),
        )
