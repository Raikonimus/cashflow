---
id: 007-journal-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 007-journal-screen

## User Story

**As any** user
**I want** to view journal lines with filters and perform bulk operations
**So that** I can analyse and correct my mandant's transactions

## Acceptance Criteria

- [ ] /journal: Tabelle (Valutadatum, Buchungsdatum, Text, Partner, IBAN, Betrag, Währung, Konto)
- [ ] Filter-Bar: Jahr, Monat, Konto (Dropdown), Partner (Autocomplete), „ohne Partner"
- [ ] Paginierung (Seitenweise oder Load-More)
- [ ] Checkbox-Auswahl mehrerer Zeilen für Bulk-Aktionen (Accountant+)
- [ ] Bulk-Aktion: „Partner zuweisen" (Autocomplete-Dialog) → POST bulk-assign
- [ ] Viewer: kein Bulk-Aktions-Bereich, aber voller Lesezugriff

## Dependencies

### Requires
- 001-auth-screens.md
- 006-journal-viewer/002-bulk-assign-partner.md
