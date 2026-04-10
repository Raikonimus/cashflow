---
id: 011-settings-keyword-config
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 011-settings-keyword-config

## User Story

**As an** Accountant
**I want** to manage keyword rules for automatic service type detection
**So that** employee and authority services are recognized using business-specific terminology

## Acceptance Criteria

- [ ] /settings/service-keywords zeigt Regeln gruppiert nach Zieltyp (`employee`, `authority`)
- [ ] Jede Regel zeigt Pattern und Pattern-Typ klar unterscheidbar als String oder Regex
- [ ] Neue Regel anlegen und bestehende Regel ändern oder löschen ist möglich
- [ ] Ungültige Regex wird inline validiert und blockiert das Speichern
- [ ] Änderungen werden nach Speichern bestätigt und wirken auf künftige automatische Typ-Ermittlungen

## Dependencies

### Requires
- 001-auth-screens.md
- 008-service-management/004-keyword-config.md
