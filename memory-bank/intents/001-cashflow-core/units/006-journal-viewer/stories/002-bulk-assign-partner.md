---
id: 002-bulk-assign-partner
unit: 006-journal-viewer
intent: 001-cashflow-core
status: draft
priority: should
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-bulk-assign-partner

## User Story

**As an** Accountant
**I want** to assign a partner to multiple journal lines at once
**So that** I can efficiently correct many lines in one action

## Acceptance Criteria

- [ ] **Given** list of line_ids and a partner_id, **When** POST /journal/bulk-assign, **Then** all lines updated
- [ ] **Given** line_id belonging to another mandant, **When** bulk-assign, **Then** 403 (silently skip or error — error preferred)
- [ ] **Given** Viewer, **When** POST /journal/bulk-assign, **Then** 403
- [ ] **Given** bulk assign completes, **When** audit_log, **Then** one entry with line count and partner_id

## Dependencies

### Requires
- 001-journal-lines-query.md
