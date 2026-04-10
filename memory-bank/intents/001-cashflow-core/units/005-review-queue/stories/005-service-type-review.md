---
id: 005-service-type-review
unit: 005-review-queue
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 005-service-type-review

## User Story

**As an** Accountant
**I want** to review automatically assigned service types and tax rates
**So that** the final classification of a service is correct and explicitly approved

## Acceptance Criteria

- [ ] **Given** a pending `service_type_review`, **When** GET /review/:id, **Then** the response contains service_id, previous_type, auto_assigned_type, reason, tax_rate, and all currently assigned journal lines for that service
- [ ] **Given** a pending item, **When** POST /review/:id/confirm, **Then** the current auto-assigned service_type remains, `service_type_manual = true`, and status → confirmed
- [ ] **Given** a pending item, **When** POST /review/:id/adjust { service_type, tax_rate? }, **Then** the service is updated, `service_type_manual = true`, optional `tax_rate_manual = true`, and status → adjusted
- [ ] **Given** a service already has a pending `service_type_review`, **When** auto-detection runs again, **Then** the existing review item is updated instead of creating a second pending item
- [ ] **Given** Viewer role, **When** review action is requested, **Then** 403

## Dependencies

### Requires
- 001-review-items-list.md
- 008-service-management/008-service-type-detection.md
