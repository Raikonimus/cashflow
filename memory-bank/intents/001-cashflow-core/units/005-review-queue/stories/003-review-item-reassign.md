---
id: 003-review-item-reassign
unit: 005-review-queue
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-review-item-reassign

## User Story

**As an** Accountant
**I want** to reassign a journal line to a different partner or create a new partner
**So that** incorrect automatic assignments are corrected

## Acceptance Criteria

- [ ] **Given** pending item, **When** POST /review/:id/reassign { partner_id }, **Then** journal_line.partner_id updated; item status → adjusted
- [ ] **Given** pending item, **When** POST /review/:id/new-partner { name }, **Then** new partner created, journal_line.partner_id = new partner; item status → adjusted
- [ ] **Given** reassign to non-existent partner_id, **When** POST, **Then** 404
- [ ] **Given** adjustment, **When** complete, **Then** audit_log entry written

## Dependencies

### Requires
- 001-review-items-list.md
- 003-partner-management/001-partner-crud.md
