---
id: 005-partner-screens
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 005-partner-screens

## User Story

**As an** Accountant
**I want** to view and manage partners including their IBANs, name variants, patterns, and merge functionality
**So that** I can maintain a clean partner master data set

## Acceptance Criteria

- [ ] /partners: Tabelle mit Name, IBAN-Anzahl, Namensvarianten-Anzahl und deduplizierten Service-Typ-Icons; Suche/Filter
- [ ] /partners/:id: IBANs-Liste, Namensliste, Muster-Liste; je mit Add/Delete
- [ ] Pattern hinzufügen: Typ (string/regex) auswählen, Muster eingeben, Regex-Fehler inline anzeigen
- [ ] Merge-Button: öffnet Dialog mit Partner-Suche (Autocomplete), Bestätigung mit Warnung
- [ ] Partnerliste: gleiche Service-Typen werden pro Partner nicht mehrfach als Icon angezeigt
- [ ] Viewer: alle Screens read-only (keine Add/Delete/Merge-Buttons)

## Technical Notes

- Service-Typ-Icons basieren auf den aktuell vorhandenen Leistungen des Partners, inklusive Basisleistung
- Icon-Daten sollen nach Freigabe oder manueller Änderung eines Service-Typs ohne Hard-Reload aktualisiert werden

## Dependencies

### Requires
- 001-auth-screens.md
- 003-partner-management/004-partner-merge.md
