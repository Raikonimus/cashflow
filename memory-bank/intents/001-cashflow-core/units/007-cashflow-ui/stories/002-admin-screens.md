---
id: 002-admin-screens
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-admin-screens

## User Story

**As an** Admin or Mandant-Admin
**I want** to manage users and mandants via the web UI
**So that** I can control access without touching the database

## Acceptance Criteria

- [ ] /admin/users: Tabelle aller User mit Rolle, Mandanten, Status; Button „User anlegen", „Deaktivieren"
- [ ] User-Dialog: E-Mail, Rolle (rollenspezifisch eingeschränkt), Mandanten-Zuweisung
- [ ] /admin/mandants (Admin only): Liste aller Mandanten; Anlegen, Bearbeiten
- [ ] Mandant-Admin sieht /admin/users (nur eigene Mandanten), kein /admin/mandants
- [ ] Zugriffsschutz: Routes mit RequireRole-Guard

## Dependencies

### Requires
- 001-auth-screens.md
- 001-identity-access/003-user-crud.md
