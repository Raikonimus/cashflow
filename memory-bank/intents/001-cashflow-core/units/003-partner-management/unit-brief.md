---
unit: 003-partner-management
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-10T00:00:00Z
---

# Unit Brief: partner-management

## Purpose

Verwaltung von Partnerunternehmen (Kunden, Lieferanten, Behörden) inkl. ihrer IBANs, Namensvarianten und Erkennungsmuster. Bietet außerdem die Zusammenführ-Funktion (Merge) zweier Partner.

## Scope

### In Scope
- Partner anlegen, bearbeiten, deaktivieren
- Mehrere IBANs pro Partner verwalten
- Mehrere Namensvarianten pro Partner verwalten
- String- und Regex-Erkennungsmuster definieren (Validierung der Regex)
- Partner-Merge: Buchungszeilen umschreiben, aufgelösten Partner deaktivieren
- Partner-Suche (für Autocomplete im UI)

### Out of Scope
- Automatische Partner-Erkennung beim Import (→ 004-import-pipeline)
- Review-Item-Erzeugung (→ 004-import-pipeline)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-7 | Partner-Stammdatenverwaltung, IBAN/Name, Muster, Merge | Must |
| FR-21 | Partner-Zusammenlegung mit Leistungs-Revalidierung | Must |

---

## Domain Concepts

### Key Entities
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Partner | Partnerunternehmen | id, mandant_id, is_active |
| PartnerName | Namensvariante | id, partner_id, name |
| PartnerIban | IBAN eines Partners | id, partner_id, iban |
| PartnerNamePattern | Erkennungsmuster | id, partner_id, pattern, pattern_type (string\|regex) |

### Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| create_partner | Legt neuen Partner an | mandant_id, name, iban? | Partner |
| add_iban | Fügt IBAN zu Partner hinzu | partner_id, iban | PartnerIban |
| add_name | Fügt Namensvariante hinzu | partner_id, name | PartnerName |
| add_pattern | Fügt Muster hinzu (Regex validieren) | partner_id, pattern, type | PartnerNamePattern |
| merge_partners | Zusammenführen zweier Partner | source_id, target_id | Partner (target) |
| find_by_iban | Sucht Partner anhand IBAN | mandant_id, iban | Partner\|None |
| find_by_name_exact | Sucht Partner per Exakt-Name | mandant_id, name | Partner\|None |
| search_partners | Autocomplete-Suche | mandant_id, query | Partner[] |

### Merge-Logik
1. Alle `journal_lines.partner_id` von `source` → `target` umschreiben
2. Alle `partner_names`, `partner_ibans`, `partner_name_patterns` von `source` → `target` verschieben
3. `source` Partner auf `is_active = false` setzen
4. Leistungs-Revalidierung für alle betroffenen Buchungszeilen des Ziel-Partners auslösen
5. Audit-Log-Eintrag

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 4 |
| Must Have | 4 |
| Should Have | 0 |
| Could Have | 0 |

### Stories
- 001-partner-crud.md
- 002-partner-iban-names.md
- 003-partner-name-patterns.md
- 004-partner-merge.md
