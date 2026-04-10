---
id: 012-operations-ui
unit: 007-cashflow-ui
intent: 001-cashflow-core
type: simple-construction-bolt
status: complete
stories:
  - 005-partner-screens
  - 006-review-queue-screen
  - 007-journal-screen
  - 008-audit-log-screen
created: 2026-04-07T14:00:00Z
started: 2026-04-07T14:00:00Z
completed: 2026-04-07T14:30:00Z
current_stage: test
stages_completed: [plan, implement, test]

requires_bolts: [011-core-ui, 005-partner-merge, 008-review-queue, 009-journal-audit]
enables_bolts: []
requires_units: []
blocks: false
---

# Bolt 012 – Operations UI

## Purpose

Implements the remaining four frontend screens:
- **Partner Management** — list, detail (IBANs/names/patterns), merge dialog
- **Review Queue** — list pending items with confirm/reassign/new-partner actions
- **Journal** — filterable table with bulk-assign
- **Audit Log** — admin-only audit event table

## Implementation Plan

### Partner Screens
- `pages/partners/PartnersPage.tsx` — searchable table
- `pages/partners/PartnerDetailPage.tsx` — IBANs, names, patterns, merge button
- `pages/partners/MergeDialog.tsx` — partner autocomplete + confirm
- `api/partners.ts` — API layer wrapped around existing backend

### Review Queue
- `pages/review/ReviewPage.tsx` — card list + actions (confirm/reassign/new partner)
- `api/review.ts`

### Journal
- `pages/journal/JournalPage.tsx` — filter bar + table + bulk-assign
- `api/journal.ts`

### Audit Log
- `pages/admin/AuditLogPage.tsx` — admin-only table with expandable details
- Reuses existing `/admin` RequireRole guard

### Router
- Add `/partners`, `/journal`, `/review`, `/admin/audit` routes to `router/index.tsx`
