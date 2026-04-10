---
id: 001-auth-screens
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-auth-screens

## User Story

**As a** user
**I want** to log in, select my mandant, and reset my password via the web UI
**So that** I can access the system from any browser

## Acceptance Criteria

- [ ] Login-Screen: E-Mail + Passwort-Felder, Submit-Button, Link „Passwort vergessen"
- [ ] Nach erfolgreichem Login mit 1 Mandant: direkt zur Hauptseite
- [ ] Nach erfolgreichem Login mit > 1 Mandant: Mandanten-Auswahl-Screen
- [ ] Passwort-vergessen-Screen: E-Mail eingeben, Erfolgs-Toast
- [ ] Reset-Password-Screen (per Token-Link): Neues PW + Bestätigung, Validierung
- [ ] Nicht-eingeloggter Zugriff auf geschützte Route: Redirect zu /login

## Dependencies

### Requires
- 001-identity-access/001-login-jwt.md
