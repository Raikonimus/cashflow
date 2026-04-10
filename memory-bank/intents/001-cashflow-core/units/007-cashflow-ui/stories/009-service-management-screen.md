---
id: 009-service-management-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 009-service-management-screen

## User Story

**As an** Accountant
**I want** to manage services and their matchers for a partner
**So that** booking lines can be assigned correctly and transparently

## Acceptance Criteria

- [ ] /partners/:id/services zeigt alle Leistungen des Partners inklusive Basisleistung, Typ, Steuersatz, Geltungszeitraum und Matcher-Anzahl
- [ ] Neue Leistung anlegen: Name, Beschreibung, Service-Typ, Steuersatz, valid_from, valid_to
- [ ] Matcher hinzufügen, bearbeiten und löschen: Pattern-Typ klar als String oder Regex erkennbar; Regex-Fehler inline sichtbar
- [ ] Basisleistung ist visuell als Basisleistung markiert; Name nicht editierbar, Löschen und Matcher-Aktionen sind deaktiviert
- [ ] Änderungen an Leistung oder Matchern zeigen nach Speichern einen Hinweis, dass Revalidierungsvorschläge erzeugt wurden

## Dependencies

### Requires
- 005-partner-screens.md
- 008-service-management/001-service-crud.md
- 008-service-management/002-service-matchers.md
- 008-service-management/003-base-service-protection.md
