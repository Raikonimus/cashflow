---
id: 006-review-queue-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 006-review-queue-screen

## User Story

**As an** Accountant
**I want** to review and resolve automatic decisions from the UI
**So that** partner assignments, service assignments, and service-type decisions are verified or corrected efficiently

## Acceptance Criteria

- [ ] /review: Liste aller pending Items; Badge in Navigation zeigt Anzahl
- [ ] Jede Karte zeigt je nach Typ die relevanten Daten: Buchungszeile (Datum, Text, Betrag), Partner, bisherige Zuordnung, vorgeschlagene Zuordnung oder automatisch gesetzten Service-Typ, plus Grund
- [ ] Aktionen je Karte: für `partner_name_match` „Bestätigen", „Anderer Partner", „Neuer Partner"; für `service_assignment` „Vorschlag übernehmen", „Andere Leistung", „Ablehnen"
- [ ] Service-Type-Reviews sind aus der Queue erreichbar und zeigen einen klaren CTA zur Freigabe oder Korrektur
- [ ] Nach Aktion: Item verschwindet aus Liste; Toast-Bestätigung
- [ ] Leere Queue: Leer-State mit Illustration

## Technical Notes

- UI muss die unterschiedlichen Review-Typen visuell eindeutig unterscheiden
- Archiv ist aus der Review-Navigation erreichbar

## Dependencies

### Requires
- 001-auth-screens.md
- 005-review-queue/003-review-item-reassign.md
- 005-review-queue/004-service-assignment-review.md
- 005-review-queue/005-service-type-review.md
