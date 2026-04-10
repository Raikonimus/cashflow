---
id: 003-account-management-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-account-management-screen

## User Story

**As an** Accountant or Mandant-Admin
**I want** to manage accounts and their CSV column mappings via the UI
**So that** I can configure imports without developer help

## Acceptance Criteria

- [ ] /accounts: Liste aller Konten mit Typ-Icon, Name, Mapping-Status (konfiguriert/ausstehend)
- [ ] /accounts/new: Formular für neues Konto (Name, Beschreibung, Typ) — eigener Screen, kein Modal
- [ ] /accounts/:id: Detail mit Konto-Infos + Mapping-Editor
- [ ] Mapping-Editor: Spalten aus CSV-Vorschau (Upload einer Muster-CSV) zu Zielspalten zuordnen (Dropdown)
- [ ] Mehrfach-Mapping: mehrere Quellspalten zu gleicher Zielspalte möglich (Drag & Drop Reihenfolge)
- [ ] „Mapping speichern" → Bestätigungs-Dialog ob Re-Mapping gewünscht
- [ ] Viewer sieht Mapping read-only; kein Edit-Button

## Dependencies

### Requires
- 001-auth-screens.md
- 002-tenant-account-mgmt/003-column-mapping-config.md
