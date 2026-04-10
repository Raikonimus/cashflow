---
id: 004-import-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-import-screen

## User Story

**As an** Accountant
**I want** to import CSV files via a guided UI with drag & drop
**So that** I can upload bank statements without technical knowledge

## Acceptance Criteria

- [ ] Step 1: Konto-Auswahl (Dropdown) oder „Neues Konto anlegen“ → Weiterleitung zu /accounts/new (eigener Screen); nach Speichern Redirect zurück zum Import mit vorausgewähltem neuem Konto
- [ ] Step 2 (nur wenn kein Mapping): Mapping-Editor inline (gleiche Komponente wie /accounts/:id)
- [ ] Step 3: CSV Drag & Drop Zone (mehrere Dateien), Dateiliste mit Remove-Button
- [ ] Step 3: „Import starten"-Button; Ladeindikator während Upload
- [ ] Step 4: Ergebnis-Screen: Anzahl importierter Zeilen, Anzahl Review-Items, Link zu Review-Queue
- [ ] Nur Accountant/Admin hat Zugriff; Viewer erhält 403-Hinweisseite

## Dependencies

### Requires
- 003-account-management-screen.md
- 004-import-pipeline/001-csv-upload-endpoint.md
