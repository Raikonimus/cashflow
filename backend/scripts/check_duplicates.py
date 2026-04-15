"""Vergleicht eine CSV-Datei gegen bestehende Journal-Einträge in der DB
und gibt alle Zeilen aus, die als Duplikat erkannt würden.

Verwendet dieselbe Duplikaterkennung wie der Import:
  - Fingerabdruck aus den mit duplicate_check=True markierten Spalten
  - Vergleich gegen _cashflow_source_values bzw. Top-Level-Werte in unmapped_data

Aufruf:
    python scripts/check_duplicates.py <pfad/zur/csv>
    python scripts/check_duplicates.py <pfad/zur/csv> --account-id <uuid>
"""

import argparse
import csv
import io
import json
import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "cashflow.db"
SOURCE_VALUES_KEY = "_cashflow_source_values"


# --------------------------------------------------------------------------- #
# Encoding / Delimiter detection (identisch mit import service)
# --------------------------------------------------------------------------- #

def _detect_encoding(raw: bytes) -> str:
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return 'utf-16'
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return 'utf-8'


def _detect_delimiter(text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        return ";"


# --------------------------------------------------------------------------- #
# Fingerabdruck (identisch mit _build_duplicate_signature)
# --------------------------------------------------------------------------- #

def _build_signature(values: dict[str, str], sources: list[str]) -> tuple | None:
    if not sources:
        return None
    if any(s not in values for s in sources):
        return None
    return tuple(sorted((s, values[s]) for s in sources))


def _extract_stored(unmapped_data: object) -> dict[str, str]:
    if not isinstance(unmapped_data, dict):
        return {}
    extracted = {
        k: v for k, v in unmapped_data.items()
        if isinstance(k, str) and k != SOURCE_VALUES_KEY and isinstance(v, str)
    }
    raw = unmapped_data.get(SOURCE_VALUES_KEY)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str):
                extracted[k] = v
    return extracted


# --------------------------------------------------------------------------- #
# Hauptlogik
# --------------------------------------------------------------------------- #

def load_duplicate_sources(conn: sqlite3.Connection, account_id: str) -> list[str]:
    cur = conn.execute(
        "SELECT column_assignments FROM column_mapping_configs WHERE account_id = ?",
        (account_id,),
    )
    row = cur.fetchone()
    if not row:
        sys.exit(f"Keine Spaltenzuordnung für Account {account_id!r} gefunden.")
    assignments = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    sources = [
        a["source"] for a in assignments
        if a.get("duplicate_check") and a.get("source")
    ]
    return sorted(dict.fromkeys(sources))


def load_existing_signatures(
    conn: sqlite3.Connection, account_id: str, duplicate_sources: list[str]
) -> dict[tuple, dict]:
    """Gibt {signatur: {valuta_date, text, amount, import_run_id}} zurück."""
    cur = conn.execute(
        "SELECT id, valuta_date, text, unmapped_data, import_run_id"
        " FROM journal_lines WHERE account_id = ?",
        (account_id,),
    )
    result: dict[tuple, dict] = {}
    for row in cur.fetchall():
        raw_unmapped = row[3]
        unmapped = json.loads(raw_unmapped) if raw_unmapped else {}
        values = _extract_stored(unmapped)
        sig = _build_signature(values, duplicate_sources)
        if sig is not None:
            result[sig] = {
                "id": row[0],
                "valuta_date": row[1],
                "text": row[2],
                "import_run_id": row[4],
            }
    return result


def find_duplicates_in_csv(
    csv_path: Path,
    existing_signatures: dict[tuple, dict],
    duplicate_sources: list[str],
) -> list[dict]:
    raw = csv_path.read_bytes()
    encoding = _detect_encoding(raw)
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    duplicates: list[dict] = []
    for row_num, row in enumerate(reader, start=2):
        values = {k: (v or "").strip() for k, v in row.items()}
        sig = _build_signature(values, duplicate_sources)
        if sig is None:
            continue
        if sig in existing_signatures:
            existing = existing_signatures[sig]
            duplicates.append({
                "csv_row": row_num,
                "valuta_date": values.get("Valutadatum", ""),
                "text": values.get("Buchungs-Details", ""),
                "amount": values.get("Betrag", ""),
                "buchungsreferenz": values.get("Buchungsreferenz", ""),
                "matched_db_id": existing["id"],
                "matched_import_run": existing["import_run_id"],
            })

    return duplicates


def find_account_id(conn: sqlite3.Connection, csv_path: Path) -> str:
    """Versucht die Account-ID aus dem Dateinamen (IBAN) zu ermitteln."""
    stem = csv_path.stem  # z.B. AT112011184376189300_2025-01-01_2025-12-31
    iban = stem.split("_")[0]
    # IBAN ist nicht direkt in accounts gespeichert — Fallback auf einziges Konto mit Mapping
    cur = conn.execute("SELECT DISTINCT account_id FROM column_mapping_configs")
    rows = cur.fetchall()
    if len(rows) == 1:
        return rows[0][0]
    print(f"Mehrere Accounts gefunden. Bitte --account-id angeben. Verfügbar:")
    for r in rows:
        print(f"  {r[0]}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dublettencheck für CSV vs. DB")
    parser.add_argument("csv", type=Path, help="Pfad zur CSV-Datei")
    parser.add_argument("--account-id", help="Account-UUID (optional, wird sonst auto-erkannt)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"DB-Pfad (Standard: {DB_PATH})")
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"CSV nicht gefunden: {args.csv}")
    if not args.db.exists():
        sys.exit(f"Datenbank nicht gefunden: {args.db}")

    conn = sqlite3.connect(str(args.db))

    account_id = args.account_id or find_account_id(conn, args.csv)
    print(f"Account-ID: {account_id}")

    duplicate_sources = load_duplicate_sources(conn, account_id)
    print(f"Dublettenprüfung-Spalten: {duplicate_sources}")

    existing_sigs = load_existing_signatures(conn, account_id, duplicate_sources)
    print(f"Bestehende DB-Einträge mit Signatur: {len(existing_sigs)}")
    print()

    duplicates = find_duplicates_in_csv(args.csv, existing_sigs, duplicate_sources)

    if not duplicates:
        print("Keine Dubletten gefunden.")
        return

    print(f"{'='*80}")
    print(f"  {len(duplicates)} Dubletten gefunden")
    print(f"{'='*80}")
    for d in duplicates:
        print(
            f"  CSV-Zeile {d['csv_row']:4d} | {d['valuta_date']:10s} | "
            f"{d['amount']:>12s} | {d['text'][:35]:<35s} | ref: {d['buchungsreferenz']}"
        )
        print(
            f"            {'':<4s}   -> DB-Eintrag: {d['matched_db_id']}  "
            f"(Run: {d['matched_import_run']})"
        )
    print(f"{'='*80}")
    print(f"  Gesamt: {len(duplicates)} Dubletten / CSV hat {len(duplicates)} doppelte Zeilen")


if __name__ == "__main__":
    main()
