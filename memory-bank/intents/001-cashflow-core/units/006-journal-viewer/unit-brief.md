---
unit: 006-journal-viewer
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-06T00:00:00Z
---

# Unit Brief: journal-viewer

## Purpose

Bereitstellung der Buchungszeilen-Abfrage-API mit umfangreichen Filtern sowie Bulk-Operationen und Audit-Log-Zugriff.

## Scope

### In Scope
- Buchungszeilen-Abfrage mit Filtern (Konto, Partner, Datum, Status)
- Paginierung
- Bulk-Partner-Zuweisung für mehrere Buchungszeilen
- Audit-Log-API (les-only, für Admin und Mandant-Admin)

### Out of Scope
- Import der Buchungszeilen (→ 004-import-pipeline)
- Partner-Stammdatenpflege (→ 003-partner-management)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-9 | Buchungszeilen-Anzeige mit Filtern | Must |
| FR-10 | Bulk-Operationen auf Buchungszeilen | Should |
| FR-11 | Audit-Log (Leseendpunkt) | Must |

---

## Domain Concepts

### Filter-Parameter für journal_lines
| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| account_id | UUID | Filtert auf ein Konto |
| partner_id | UUID | Filtert auf einen Partner |
| year | int | Filtert Valutadatum nach Jahr |
| month | int | Filtert Valutadatum nach Monat |
| has_partner | bool | Nur Zeilen mit/ohne Partner |
| page / page_size | int | Paginierung |

### Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| list_journal_lines | Paginierte Abfrage | mandant_id, filter params | Page[JournalLine] |
| bulk_assign_partner | Partner für mehrere Zeilen setzen | line_ids[], partner_id | updated_count |
| list_audit_log | Audit-Log-Einträge lesen | mandant_id, filter? | AuditLog[] |

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 3 |
| Must Have | 3 |
| Should Have | 1 |
| Could Have | 0 |

### Stories
- 001-journal-lines-query.md
- 002-bulk-assign-partner.md
- 003-audit-log-api.md
