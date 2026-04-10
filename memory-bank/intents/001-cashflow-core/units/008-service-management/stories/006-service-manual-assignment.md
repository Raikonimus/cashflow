---
id: 006-service-manual-assignment
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 006-service-manual-assignment

## User Story

**As an** Accountant
**I want** to manually assign a service to a journal line
**So that** I can correct or refine service classification when automation is insufficient

## Acceptance Criteria

- [ ] **Given** a journal line, **When** POST /journal/:id/assign-service { service_id }, **Then** the selected service is stored and `service_assignment_mode = manual`
- [ ] **Given** the selected service belongs to a different partner than the journal line, **When** assignment is requested, **Then** 422
- [ ] **Given** the selected service validity window does not include the journal line booking_date, **When** assignment is requested, **Then** 422
- [ ] **Given** the selected service is valid for the line, **When** assignment succeeds, **Then** no automatic reassignment occurs until a later revalidation creates a proposal

## Dependencies

### Requires
- 001-service-crud.md
- 005-service-auto-assignment.md
