---
id: 006-review-archive
unit: 005-review-queue
intent: 001-cashflow-core
status: ready
priority: should
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 006-review-archive

## User Story

**As an** Accountant
**I want** to browse resolved review items in an archive
**So that** I can understand past decisions and audit corrections later

## Acceptance Criteria

- [ ] **Given** resolved review items exist, **When** GET /review/archive, **Then** items with status confirmed, adjusted, or rejected are returned paginated
- [ ] **Given** filters `item_type`, `resolved_by_user_id`, or date range, **When** GET /review/archive, **Then** only matching items are returned
- [ ] **Given** archive results, **When** rendered, **Then** they are sorted by `resolved_at DESC` by default
- [ ] **Given** an archived item, **When** a write action is attempted, **Then** 409 because archived items are no longer actionable

## Dependencies

### Requires
- 004-service-assignment-review.md
- 005-service-type-review.md
