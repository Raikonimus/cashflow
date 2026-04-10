---
id: 010-service-type-review-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 010-service-type-review-screen

## User Story

**As an** Accountant
**I want** to review automatically set service types in a dedicated UI
**So that** I can approve or correct the classification with full context

## Acceptance Criteria

- [ ] /review/service-types zeigt alle offenen Service-Type-Reviews mit Service-Name, aktuellem Typ, Grund und Anzahl aktuell zugeordneter Buchungszeilen
- [ ] Detailansicht zeigt alle aktuell der Leistung zugeordneten Buchungszeilen
- [ ] Aktionen: „Freigeben" belässt den automatisch gesetzten Typ, „Korrigieren" erlaubt Typ- und optional Steuersatzänderung
- [ ] Nach erfolgreicher Aktion verschwindet der Eintrag aus der offenen Liste und erscheint im Archiv
- [ ] Manuell oder bereits freigegebene Typen werden klar gekennzeichnet

## Dependencies

### Requires
- 006-review-queue-screen.md
- 005-review-queue/005-service-type-review.md
