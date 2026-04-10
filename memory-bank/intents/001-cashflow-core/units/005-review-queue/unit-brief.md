---
unit: 005-review-queue
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-10T00:00:00Z
---

# Unit Brief: review-queue

## Purpose

Bereitstellung und Auflösung der Review-Queue: Zeigt automatische Entscheidungen mit Unsicherheit und ermöglicht deren Bestätigung oder Korrektur.

## Scope

### In Scope
- Review-Items auflisten (Filter: mandant, status, type) inklusive Archiv
- Review-Item bestätigen (partner_name_match → ok)
- Review-Item anpassen: anderen Partner zuweisen
- Review-Item anpassen: neuer Partner anlegen
- Review-Item bestätigen, anpassen oder ablehnen (service_assignment)
- Service-Type-Review freigeben oder korrigieren
- `journal_line.partner_id` und `journal_line.service_id` bei Korrektur aktualisieren
- Zähler: offene Review-Items (für UI-Badge)

### Out of Scope
- Review-Item-Erstellung (→ 004-import-pipeline)
- Partner-Anlage im Detail (→ 003-partner-management)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-8 | Review Queue | Must |
| FR-18 | Review-Inbox – Service-Type-Review | Must |
| FR-19 | Review-Inbox – Leistungszuordnungs-Review | Must |
| FR-20 | Review-Archiv | Should |

---

## Domain Concepts

### Review-Item-Typen (aktuell)
| Type | Beschreibung | Mögliche Aktionen |
|------|-------------|-------------------|
| partner_name_match | Partner per Namensgleichheit zugeordnet, aber IBAN neu/unbekannt | bestätigen, anderer Partner, neuer Partner |
| service_assignment | Revalidierungsvorschlag oder Mehrfachtreffer bei Leistungszuordnung | bestätigen (Vorschlag übernehmen), anpassen, ablehnen |
| service_type_review | Automatisch gesetzter Service-Typ muss freigegeben oder korrigiert werden | freigeben, korrigieren |

### Review-Status
| Status | Bedeutung |
|--------|-----------|
| pending | Offen und aktionierbar |
| confirmed | Vorschlag oder automatische Entscheidung wurde übernommen |
| adjusted | Vorschlag wurde manuell abgeändert |
| rejected | Vorschlag wurde bewusst verworfen |

### Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| list_review_items | Listet Items nach Filter | mandant_id, status?, type? | ReviewItem[] |
| confirm_item | Bestätigt automatische Entscheidung oder übernimmt Vorschlag | item_id | ReviewItem (confirmed) |
| reassign_partner | Weist anderen Partner zu | item_id, new_partner_id | ReviewItem, JournalLine updated |
| create_new_partner | Legt neuen Partner an, weist zu | item_id, partner_name | ReviewItem, Partner, JournalLine updated |
| confirm_service_assignment | Übernimmt vorgeschlagene Leistung | item_id | ReviewItem, JournalLine updated |
| adjust_service_assignment | Setzt andere Leistung | item_id, service_id | ReviewItem, JournalLine updated |
| reject_service_assignment | Verwirft Vorschlag | item_id | ReviewItem (rejected) |
| confirm_service_type | Gibt automatisch gesetzten Typ frei | item_id | ReviewItem, Service updated |
| adjust_service_type | Korrigiert Typ oder Steuersatz | item_id, service_type?, tax_rate? | ReviewItem, Service updated |
| count_pending | Zählt offene Items | mandant_id | int |

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 6 |
| Must Have | 5 |
| Should Have | 1 |
| Could Have | 0 |

### Stories
- 001-review-items-list.md
- 002-review-item-confirm.md
- 003-review-item-reassign.md
- 004-service-assignment-review.md
- 005-service-type-review.md
- 006-review-archive.md
