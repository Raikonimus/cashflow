---
unit: 002-tenant-account-mgmt
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-06T00:00:00Z
---

# Unit Brief: tenant-account-mgmt

## Purpose

Verwaltung von Mandanten und deren Konten (Bankkonten, Kreditkarten, Sonstige) sowie die Konfiguration des CSV-Spalten-Mappings pro Konto.

## Scope

### In Scope
- Mandanten anlegen, bearbeiten, deaktivieren
- Konten anlegen, bearbeiten, löschen
- Column-Mapping konfigurieren (Quellspalte → Zielspalte, Mehrfach-Mapping)
- Re-Mapping-Trigger: optionale Neuanwendung auf bestehende Buchungszeilen

### Out of Scope
- User-Verwaltung (→ 001-identity-access)
- Import der Buchungszeilen (→ 004-import-pipeline)
- Buchungszeilen-Anzeige (→ 006-journal-viewer)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-3 | Mandanten- & Kontoverwaltung | Must |
| FR-4 | CSV-Spalten-Mapping pro Konto | Must |

---

## Domain Concepts

### Key Entities
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Mandant | Unternehmen/Tenant | id, name, is_active |
| Account | Konto/Kreditkarte eines Mandanten | id, mandant_id, name, description, account_type |
| ColumnMapping | Mapping Quellspalte → Zielspalte | id, account_id, source_column, target_column, sort_order |

### Zielspalten (target_column Wertemenge)
`valuta_date`, `booking_date`, `text`, `partner_name`, `partner_iban`, `amount`, `currency`

### Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| create_mandant | Legt neuen Mandanten an | name | Mandant |
| create_account | Legt Konto für Mandanten an | mandant_id, name, type | Account |
| set_column_mapping | Definiert/ersetzt Mapping für ein Konto | account_id, mappings[] | ColumnMapping[] |
| get_mapping_for_account | Liefert aktives Mapping | account_id | ColumnMapping[] |
| trigger_remapping | Neuverarbeitung der Buchungszeilen | account_id, dry_run | affected_count |

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 4 |
| Must Have | 4 |
| Should Have | 0 |
| Could Have | 0 |

### Stories
- 001-mandant-crud.md
- 002-account-crud.md
- 003-column-mapping-config.md
- 004-remapping-trigger.md
