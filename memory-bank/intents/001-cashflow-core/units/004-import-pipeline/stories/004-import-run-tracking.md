---
id: 004-import-run-tracking
unit: 004-import-pipeline
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-import-run-tracking

## User Story

**As an** Accountant
**I want** to see a history of all import runs
**So that** I can track what was imported when and by whom

## Acceptance Criteria

- [ ] **Given** completed import, **When** GET /imports?account_id=, **Then** list shows user, date, filename, row_count, status
- [ ] **Given** import error, **When** GET /imports/:id, **Then** shows status=failed and error details
- [ ] **Given** import in progress, **When** GET /imports/:id, **Then** shows status=pending
- [ ] **Given** completed import, **When** GET /imports/:id, **Then** shows status=completed with row_count

## Dependencies

### Requires
- 001-csv-upload-endpoint.md
