---
id: 001-review-items-list
unit: 005-review-queue
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-review-items-list

## User Story

**As an** Accountant
**I want** to see all pending review items
**So that** I can check and confirm automatic decisions

## Acceptance Criteria

- [ ] **Given** pending items exist, **When** GET /review, **Then** list sorted by created_at ASC
- [ ] **Given** filter status=pending, **When** GET /review, **Then** only pending items returned
- [ ] **Given** no pending items, **When** GET /review, **Then** returns empty list (not 404)
- [ ] **Given** Viewer, **When** GET /review, **Then** 403

## Dependencies

### Requires
- 004-import-pipeline/003-partner-matching.md
