---
id: 008-audit-log-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 008-audit-log-screen

## User Story

**As an** Admin or Mandant-Admin
**I want** to view the audit log in the UI
**So that** I can trace any action performed in the system

## Acceptance Criteria

- [ ] /admin/audit: Tabelle (Datum, User, Aktion, Entity-Typ, Entity-ID, Vorher/Nachher-Button)
- [ ] Filter: User, Zeitraum, Aktion-Typ
- [ ] Klick auf „Details": expandiert old_value / new_value als JSON
- [ ] Accountant und Viewer: 403 bei /admin/audit

## Dependencies

### Requires
- 002-admin-screens.md
- 006-journal-viewer/003-audit-log-api.md
