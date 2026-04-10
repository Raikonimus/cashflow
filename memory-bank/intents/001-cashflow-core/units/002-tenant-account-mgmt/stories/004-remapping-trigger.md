---
id: 004-remapping-trigger
unit: 002-tenant-account-mgmt
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-remapping-trigger

## User Story

**As an** Accountant
**I want** to optionally re-apply an updated column mapping to all existing journal lines
**So that** historical data benefits from mapping corrections without data loss

## Acceptance Criteria

- [ ] **Given** updated mapping, **When** POST /accounts/:id/remapping?dry_run=true, **Then** returns count of affected lines without changing data
- [ ] **Given** updated mapping, **When** POST /accounts/:id/remapping, **Then** re-applies mapping to all journal lines of the account using stored unmapped_data
- [ ] **Given** journal line with no unmapped_data for a new source column, **When** remapping, **Then** field is left empty (not error)
- [ ] **Given** remapping completes, **When** check journal lines, **Then** all mapped fields are updated; unmapped_data unchanged

## Technical Notes

- Re-mapping reads from `unmapped_data` JSONB — this is why unmapped columns must be stored
- Run in a database transaction; rollback on error

## Dependencies

### Requires
- 003-column-mapping-config.md
