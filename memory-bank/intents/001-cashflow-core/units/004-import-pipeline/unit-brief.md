---
unit: 004-import-pipeline
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-10T00:00:00Z
---

# Unit Brief: import-pipeline

## Purpose

Verarbeitung von CSV-Datei-Uploads: Mapping anwenden, Buchungszeilen anlegen, Partner erkennen/anlegen und Review-Items für unsichere Zuordnungen erzeugen.

## Scope

### In Scope
- Multipart CSV-Upload (eine oder mehrere Dateien)
- Column-Mapping anwenden (Quellspalte → Zielspalte)
- Mehrere Quellspalten → gleiche Zielspalte → mit `\n` verbinden
- Nicht gemappte Spalten in `unmapped_data` JSONB speichern
- Partner-Matching (Reihenfolge: IBAN → Exakt-Name → Neu)
- Automatische Leistungszuordnung nach erfolgreicher Partner-Zuordnung
- Review-Item erzeugen bei Typ `partner_name_match`
- Review-Item erzeugen bei Leistungs-Mehrfachtreffern (`service_assignment`)
- Import-Run-Tracking (User, Datum, Dateiname, Zeilenanzahl, Status)
- Transaktionssicherheit: alles oder nichts pro Import

### Out of Scope
- Mapping-Konfiguration (→ 002-tenant-account-mgmt)
- Partner-Stammdatenpflege (→ 003-partner-management)
- Review-Item-Auflösung (→ 005-review-queue)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-5 | CSV-Import von Buchungszeilen | Must |
| FR-6 | Automatische Partner-Erkennung beim Import | Must |
| FR-14 | Automatische Leistungszuordnung beim Import | Must |

---

## Domain Concepts

### Key Entities
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| ImportRun | Protokoll eines Import-Vorgangs | id, account_id, user_id, filename, row_count, skipped_count, status |
| JournalLine | Buchungszeile | id, account_id, import_run_id, partner_id, service_id, service_assignment_mode, valuta_date, booking_date, text, partner_name_raw, partner_iban_raw, amount, currency, unmapped_data (JSONB) |
| ReviewItem | Unsichere automatische Entscheidung | id, mandant_id, item_type, journal_line_id (FK), context (JSONB), status |

### Partner-Matching-Algorithmus
```
Für jede CSV-Zeile:
  iban = zeile.partner_iban_raw

  1. IBAN-Match:
     partner = find_by_iban(mandant_id, iban)
     → wenn gefunden: journal_line.partner_id = partner.id  [sicher, kein Review-Item]

  2. Name-Match (nur wenn kein IBAN-Treffer):
     name = zeile.partner_name_raw
     partner = find_by_name_ilike(mandant_id, name)  -- case-insensitive (ILIKE)
     → wenn gefunden:
         journal_line.partner_id = partner.id
         → wenn iban nicht leer UND iban ∉ partner.ibans:
             erzeuge ReviewItem(type=partner_name_match, journal_line_id=...)
         → wenn iban leer (Buchungszeile ohne IBAN): kein Review-Item

  3. Kein Treffer:
     partner = create_partner(mandant_id, name=name, iban=iban)
     journal_line.partner_id = partner.id
     [kein Review-Item]
```

### Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| upload_csv | Empfängt Datei(en), startet Import | account_id, files[] | ImportRun |
| apply_mapping | Mappt CSV-Zeile auf interne Felder | row (dict), mappings[] | mapped_row, unmapped_data |
| match_partner | Führt Matching-Algorithmus aus | mandant_id, name, iban | partner_id, review_needed |
| assign_service_on_import | Führt Leistungszuordnung nach Partner-Match aus | journal_line_id | service_id, review_needed |
| create_import_run | Legt ImportRun an | account_id, user_id, filename | ImportRun |
| store_journal_lines | Bulk-Insert der gemappten Zeilen | lines[] | count |

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 5 |
| Must Have | 5 |
| Should Have | 0 |
| Could Have | 0 |

### Stories
- 001-csv-upload-endpoint.md
- 002-mapping-application.md
- 003-partner-matching.md
- 004-import-run-tracking.md
- 009-import-service-assignment.md
