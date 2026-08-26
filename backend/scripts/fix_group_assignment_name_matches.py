"""
Einmalig-Skript: Leistungen in die namensgleiche Gruppe verschieben.

Hintergrund: Solange die bevorzugte Standardgruppe einer Sektion nicht existierte
(z. B. "Kunden" umbenannt in "Sonstige Einnahmen"), fiel _select_default_group auf
die Gruppe mit dem niedrigsten sort_order zurueck. Neue Leistungen landeten dadurch
in einer echten Fachgruppe statt im Auffangbecken.

Dieses Skript korrigiert nur die eindeutigen Faelle: eine Leistung, deren Name exakt
(case-insensitiv) einer anderen Gruppe derselben Sektion und desselben Mandanten
entspricht, wird in diese Gruppe verschoben. Alles andere bleibt unangetastet.

Standard ist ein Dry-Run. Erst `--apply` schreibt.

    uv run python scripts/fix_group_assignment_name_matches.py
    uv run python scripts/fix_group_assignment_name_matches.py --apply
"""

import argparse
import sqlite3
from datetime import datetime, timezone

DB_PATH = "/Users/raimund/Developer/cashflow/backend/cashflow.db"

CANDIDATES_SQL = """
    SELECT
        a.id            AS assignment_id,
        p.name          AS partner_name,
        s.name          AS service_name,
        g.section       AS section,
        g.name          AS current_group_name,
        target.id       AS target_group_id,
        target.name     AS target_group_name
    FROM service_group_assignments a
    JOIN service_groups g       ON g.id = a.service_group_id
    JOIN services s             ON s.id = a.service_id
    JOIN partners p             ON p.id = s.partner_id
    JOIN service_groups target  ON target.section    = g.section
                               AND target.mandant_id = g.mandant_id
                               AND lower(target.name) = lower(s.name)
                               AND target.id <> g.id
    ORDER BY g.section, p.name, s.name
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def run(apply_changes: bool) -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute(CANDIDATES_SQL).fetchall()
    if not rows:
        print("Keine namensgleichen Fehlzuordnungen gefunden - nichts zu tun.")
        con.close()
        return 0

    # Sicherheitscheck: eine Leistung darf nur genau ein Ziel haben, sonst ist der
    # Treffer nicht eindeutig und wird uebersprungen.
    seen: dict[str, int] = {}
    for row in rows:
        seen[row["assignment_id"]] = seen.get(row["assignment_id"], 0) + 1
    ambiguous = {key for key, count in seen.items() if count > 1}

    print(f"{len(rows)} Treffer:\n")
    planned = []
    for row in rows:
        marker = "  UEBERSPRUNGEN (mehrdeutig)" if row["assignment_id"] in ambiguous else ""
        print(
            f"  [{row['section']}] {row['partner_name']} / {row['service_name']}: "
            f"{row['current_group_name']} -> {row['target_group_name']}{marker}"
        )
        if row["assignment_id"] not in ambiguous:
            planned.append(row)

    if not apply_changes:
        print(f"\nDry-Run. Mit --apply werden {len(planned)} Zuordnung(en) geschrieben.")
        con.close()
        return 0

    now = utcnow()
    for row in planned:
        cur.execute(
            "UPDATE service_group_assignments SET service_group_id = ?, updated_at = ? WHERE id = ?",
            (row["target_group_id"], now, row["assignment_id"]),
        )
    con.commit()
    print(f"\n{len(planned)} Zuordnung(en) aktualisiert.")
    con.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aenderungen schreiben (sonst Dry-Run)")
    args = parser.parse_args()
    raise SystemExit(run(args.apply))
