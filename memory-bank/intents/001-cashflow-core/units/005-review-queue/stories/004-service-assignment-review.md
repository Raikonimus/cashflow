---
id: 004-service-assignment-review
unit: 005-review-queue
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-service-assignment-review

## User Story

**As an** Accountant
**I want** to review suggested service assignment changes
**So that** the stored service assignment stays under manual control when the system detects ambiguity or changed matcher logic

## Acceptance Criteria

- [ ] **Given** a pending `service_assignment` review item, **When** GET /review, **Then** current_service_id, proposed_service_id, reason, and journal line details are returned
- [ ] **Given** a pending item, **When** POST /review/:id/confirm, **Then** `journal_line.service_id = proposed_service_id`, `service_assignment_mode = manual`, and status → confirmed
- [ ] **Given** a pending item, **When** POST /review/:id/adjust { service_id }, **Then** `journal_line.service_id` is updated to the selected service, `service_assignment_mode = manual`, and status → adjusted
- [ ] **Given** a pending item, **When** POST /review/:id/reject, **Then** the stored assignment remains unchanged and status → rejected
- [ ] **Given** the selected service belongs to another partner or is outside validity period, **When** adjust is requested, **Then** 422

## Dependencies

### Requires
- 001-review-items-list.md
- 008-service-management/006-service-manual-assignment.md
- 008-service-management/007-service-revalidation.md
