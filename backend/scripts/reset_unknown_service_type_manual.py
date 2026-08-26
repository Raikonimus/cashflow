"""
Einmalig-Skript: Automatik fuer "unbekannte" Leistungen wieder einschalten.

Hintergrund: create_service hat service_type_manual/tax_rate_manual fest auf True
gesetzt - auch dann, wenn beim Anlegen gar keine Art gewaehlt wurde und die Leistung
mit service_type='unknown' entstand. detect_service_type_for_service steigt bei
service_type_manual sofort aus, also blieb die Leistung dauerhaft 'unknown'. Ohne Art
gibt es keine Sektion, ohne Sektion keine Gruppe - und ohne Gruppe taucht die Leistung
in Einnahmen & Ausgaben nirgends auf.

Der Kombination 'unknown' + manuell kann man nicht sinnvoll folgen: "unbekannt" ist
keine Festlegung. Dieses Skript setzt genau dort die beiden Manual-Flags zurueck und
ueberlaesst den Rest der App - die Erkennung bestimmt die Art, der Reparaturlauf in
get_income_expense_matrix legt die Gruppenzuordnung an.

Leistungen mit einer echten Art (customer, supplier, internal_transfer, ...) bleiben
unangetastet, auch wenn sie keiner Gruppe angehoeren.

Standard ist ein Dry-Run. Erst `--apply` schreibt.

    uv run python scripts/reset_unknown_service_type_manual.py
    uv run python scripts/reset_unknown_service_type_manual.py --apply
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "cashflow.db"

CANDIDATES_SQL = """
    SELECT
        s.id                       AS service_id,
        p.name                     AS partner_name,
        s.name                     AS service_name,
        s.tax_rate                 AS tax_rate,
        count(sp.id)               AS split_count,
        coalesce(sum(sp.amount),0) AS split_amount,
        (SELECT count(*) FROM service_group_assignments a WHERE a.service_id = s.id) AS group_count
    FROM services s
    JOIN partners p ON p.id = s.partner_id
    LEFT JOIN journal_line_splits sp ON sp.service_id = s.id
    WHERE s.service_type = 'unknown'
      AND (s.service_type_manual = 1 OR s.tax_rate_manual = 1)
    GROUP BY s.id
    ORDER BY abs(coalesce(sum(sp.amount),0)) DESC
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def run(db_path: Path, apply_changes: bool) -> int:
    if not db_path.exists():
        print(f"Datenbank nicht gefunden: {db_path}")
        return 1

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute(CANDIDATES_SQL).fetchall()
    if not rows:
        print("Keine Leistung mit 'unknown' + manueller Festlegung gefunden - nichts zu tun.")
        con.close()
        return 0

    print(f"{len(rows)} Leistung(en) betroffen:\n")
    for row in rows:
        gruppe = "ohne Gruppe" if row["group_count"] == 0 else f"{row['group_count']} Gruppe(n)"
        print(
            f"  {row['partner_name']} / {row['service_name']}: "
            f"{row['split_count']} Buchung(en), {row['split_amount']:.2f} EUR, {gruppe}"
        )

    if not apply_changes:
        print(f"\nDry-Run. Mit --apply werden bei {len(rows)} Leistung(en) die Manual-Flags zurueckgesetzt.")
        con.close()
        return 0

    now = utcnow()
    for row in rows:
        cur.execute(
            "UPDATE services SET service_type_manual = 0, tax_rate_manual = 0, updated_at = ? WHERE id = ?",
            (now, row["service_id"]),
        )
    con.commit()
    con.close()
    print(f"\n{len(rows)} Leistung(en) aktualisiert.")
    print("Die Art wird beim naechsten Erkennungslauf gesetzt (z. B. beim Speichern der Leistung),")
    print("die Gruppenzuordnung danach automatisch beim Aufruf von Einnahmen & Ausgaben.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aenderungen schreiben (sonst Dry-Run)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help=f"Pfad zur SQLite-DB (Default: {DEFAULT_DB_PATH})")
    args = parser.parse_args()
    raise SystemExit(run(args.db, args.apply))
