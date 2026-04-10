---
id: 002-review-item-confirm
unit: 005-review-queue
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-review-item-confirm

## User Story

**As an** Accountant
**I want** to confirm an automatic partner assignment
**So that** the decision is marked as verified

## Acceptance Criteria

- [ ] **Given** pending review item, **When** POST /review/:id/confirm, **Then** status → confirmed; resolved_by = current user
- [ ] **Given** already confirmed item, **When** POST /review/:id/confirm, **Then** 409
- [ ] **Given** confirm for partner_name_match, **When** confirmed, **Then** IBAN from journal_line added to partner_ibans (so future imports match by IBAN)

## Dependencies

### Requires
- 001-review-items-list.md
