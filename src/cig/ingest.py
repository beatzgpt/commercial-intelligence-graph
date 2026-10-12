"""Load the synthetic files into SQLite. Provenance is enforced here: a signal missing any
provenance field is rejected, so nothing unsourced can reach the score."""
import csv
import json
import sqlite3
from pathlib import Path

from .config import DATA_DIR, DB_PATH, REQUIRED_SIGNAL_FIELDS

SCHEMA = """
CREATE TABLE companies (company_id TEXT PRIMARY KEY, name TEXT UNIQUE, segment TEXT, region TEXT,
                        employees INTEGER, revenue_band TEXT);
CREATE TABLE people (person_id TEXT PRIMARY KEY, name TEXT, title TEXT,
                     company_id TEXT REFERENCES companies, role_type TEXT);
CREATE TABLE technologies (tech_id TEXT PRIMARY KEY, name TEXT, category TEXT, generation TEXT);
CREATE TABLE company_technologies (company_id TEXT REFERENCES companies,
                                   tech_id TEXT REFERENCES technologies, since TEXT);
CREATE TABLE signals (signal_id TEXT PRIMARY KEY, company_id TEXT REFERENCES companies, type TEXT,
                      source_type TEXT, source_id TEXT, observed_at TEXT, evidence_url TEXT,
                      confidence REAL, summary TEXT, tech_id TEXT, person_id TEXT);
"""


class ProvenanceError(ValueError):
    pass


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _insert(conn, table, rows):
    if not rows:
        return
    cols = list(rows[0])
    conn.executemany(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [tuple(r[c] for c in cols) for r in rows],
    )


def ingest(data_dir: Path = DATA_DIR, db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for table, fname in [("companies", "companies.csv"), ("people", "people.csv"),
                         ("technologies", "technologies.csv"),
                         ("company_technologies", "company_technologies.csv")]:
        _insert(conn, table, _rows(data_dir / fname))

    signals = []
    with (data_dir / "signals.jsonl").open(encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            missing = [k for k in REQUIRED_SIGNAL_FIELDS if s.get(k) in (None, "")]
            if missing:
                raise ProvenanceError(f"{s.get('signal_id')} missing provenance fields: {missing}")
            signals.append(s)
    _insert(conn, "signals", signals)
    conn.commit()
    return conn


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
