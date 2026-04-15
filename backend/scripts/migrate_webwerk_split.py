"""
Einmalig-Skript: Webwerk-Buchungen aus Microsoft Payments herauslösen.

- Legt neuen Partner "Webwerk Online-Solutions GmbH" an
- Registriert IBAN AT823900000001082502
- Verschiebt alle 79 Buchungszeilen mit partner_iban_raw = AT823900000001082502
  vom Microsoft-Payments-Partner zum neuen Webwerk-Partner
- Legt eine Basisleistung für Webwerk an und setzt service_id der Zeilen um
- Löscht service_assignment ReviewItems für betroffene Zeilen
"""

import sqlite3
import sys
import uuid
from datetime import datetime, timezone

DB_PATH = "/Users/raimund/Developer/cashflow/backend/cashflow.db"
MANDANT_ID = "4afe231b67564828a623985815d84c84"
MS_PARTNER_ID = "cc75605cd38a499087e384723508efb0"
WEBWERK_IBAN = "AT823900000001082502"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def new_uuid() -> str:
    return uuid.uuid4().hex  # 32-char hex ohne Bindestriche


def run() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1. Sicherheitscheck
    cur.execute(
        "SELECT COUNT(*) FROM journal_lines WHERE partner_iban_raw=? AND partner_id=?",
        (WEBWERK_IBAN, MS_PARTNER_ID),
    )
    count = cur.fetchone()[0]
    print(f"Betroffene Buchungszeilen: {count}")
    if count == 0:
        print("Keine Zeilen gefunden – Abbruch.")
        con.close()
        return

    now = utcnow()

    # 2. Neuen Partner anlegen
    webwerk_id = new_uuid()
    cur.execute(
        "INSERT INTO partners (id, mandant_id, name, display_name, is_active, created_at, updated_at) "
        "VALUES (?, ?, ?, NULL, 1, ?, ?)",
        (webwerk_id, MANDANT_ID, "Webwerk Online-Solutions GmbH", now, now),
    )
    print(f"Neuer Partner: Webwerk Online-Solutions GmbH ({webwerk_id})")

    # 3. IBAN registrieren
    iban_id = new_uuid()
    cur.execute(
        "INSERT INTO partner_ibans (id, partner_id, iban, created_at) VALUES (?, ?, ?, ?)",
        (iban_id, webwerk_id, WEBWERK_IBAN, now),
    )
    print(f"IBAN registriert: {WEBWERK_IBAN}")

    # 4. Basisleistung anlegen
    service_id = new_uuid()
    cur.execute(
        "INSERT INTO services (id, partner_id, name, is_base_service, service_type, tax_rate, "
        "service_type_manual, tax_rate_manual, created_at, updated_at) "
        "VALUES (?, ?, 'Basisleistung', 1, 'unknown', 20.00, 0, 0, ?, ?)",
        (service_id, webwerk_id, now, now),
    )
    print(f"Basisleistung angelegt ({service_id})")

    # 5. Buchungszeilen umziehen
    cur.execute(
        "UPDATE journal_lines SET partner_id=?, service_id=?, service_assignment_mode='auto' "
        "WHERE partner_iban_raw=? AND partner_id=?",
        (webwerk_id, service_id, WEBWERK_IBAN, MS_PARTNER_ID),
    )
    moved = cur.rowcount
    print(f"{moved} Buchungszeilen auf Webwerk umgezogen")

    # 6. service_assignment ReviewItems für betroffene Zeilen löschen
    cur.execute(
        "DELETE FROM review_items WHERE item_type='service_assignment' "
        "AND journal_line_id IN ("
        "  SELECT id FROM journal_lines WHERE partner_id=? AND partner_iban_raw=?"
        ")",
        (webwerk_id, WEBWERK_IBAN),
    )
    deleted_reviews = cur.rowcount
    print(f"{deleted_reviews} service_assignment ReviewItems gelöscht")

    con.commit()
    con.close()
    print("\nMigration abgeschlossen ✓")
    print(f"Webwerk Partner-ID: {webwerk_id}")


if __name__ == "__main__":
    run()

