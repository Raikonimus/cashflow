---
id: 012-income-expense-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-15T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 012-income-expense-screen

## User Story

**As any** user
**I want** a dedicated income-expense screen with monthly matrix, grouping and yearly navigation
**So that** I can evaluate annual and monthly net values for each service

## Acceptance Criteria

- [ ] Navigation includes menu entry `Einnahmen & Ausgaben` and route `/cashflow/income-expense`
- [ ] Screen shows three sections: `Einnahmen`, `Ausgaben`, `Erfolgsneutrale Zahlungen`
- [ ] Table layout per section: first data column = `Jahr`, followed by `Jan`..`Dez`
- [ ] Row model: services as rows, months as columns
- [ ] Group header row shows subtotal per column; grand total row shows total per column for section
- [ ] Groups can be collapsed/expanded; collapsed groups show only group subtotal row
- [ ] Users can create groups directly in the UI for each section
- [ ] Service rows can be assigned to groups via drag & drop; assignment persists after reload
- [ ] Cross-section drag & drop is blocked with user-visible validation message
- [ ] Year switch controls (`Vorjahr`, `Folgejahr`) reload matrix data without full page reload
- [ ] Values are formatted as currency and render `0,00` for empty cells
- [ ] Viewer role has no editing controls for groups and drag & drop (read-only)

## Dependencies

### Requires
- 001-auth-screens.md
- 006-journal-viewer/004-cashflow-matrix-api.md
- 008-service-management/009-service-groups.md
