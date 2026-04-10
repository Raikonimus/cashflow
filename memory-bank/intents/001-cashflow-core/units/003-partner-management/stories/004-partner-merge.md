---
id: 004-partner-merge
unit: 003-partner-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-partner-merge

## User Story

**As an** Accountant
**I want** to merge two partners into one
**So that** duplicate partner entries are consolidated and all journal lines are correctly attributed

## Acceptance Criteria

- [ ] **Given** two active partners, **When** POST /partners/:target_id/merge { source_id }, **Then** all journal_lines.partner_id = source → target
- [ ] **Given** merge completes, **When** GET /partners/:source_id, **Then** source is inactive
- [ ] **Given** merge, **When** complete, **Then** all names, IBANs, patterns of source are moved to target
- [ ] **Given** merge completed, **When** service revalidation runs, **Then** all affected journal lines are checked against services of the target partner only
- [ ] **Given** service revalidation after merge finds deviations, **When** complete, **Then** service_assignment review items are created and existing service assignments are not auto-overwritten
- [ ] **Given** merge, **When** complete, **Then** audit_log entry created with old/new partner_id for affected lines count
- [ ] **Given** source_id == target_id, **When** POST merge, **Then** 400

## Technical Notes

- Entire merge runs in a single database transaction
- Duplicate names/IBANs after merge are deduplicated (no hard error)
- Service revalidation is triggered after partner IDs have been rewritten and merged data is committed atomically

## Dependencies

### Requires
- 001-partner-crud.md
- 002-partner-iban-names.md
