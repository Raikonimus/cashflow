---
id: 009-service-groups
unit: 008-service-management
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-15T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 009-service-groups

## User Story

**As an** Accountant
**I want** to manage income/expense/neutral groups and assign services to groups
**So that** the income-expense matrix can be structured by business-relevant categories

## Acceptance Criteria

- [ ] **Given** first access for a mandant, **When** no service groups exist, **Then** at least one default group is created per section (`income`/`expense`/`neutral`)
- [ ] **Given** valid payload, **When** POST /service-groups is called, **Then** a new group is created with section and sort order
- [ ] **Given** an existing group, **When** PATCH /service-groups/{id} is called, **Then** name and sort order can be changed
- [ ] **Given** a group with assigned services, **When** DELETE /service-groups/{id} is called, **Then** deletion is rejected unless reassignment is provided
- [ ] **Given** a service and target group in same section, **When** POST /service-group-assignments is called, **Then** the service is reassigned and persisted
- [ ] **Given** cross-section assignment attempt (`income`/`expense`/`neutral` mismatch), **When** assignment is requested, **Then** request is rejected with 422
- [ ] **Given** a request in mandant A, **When** groups/services from mandant B are referenced, **Then** request is rejected with 404/403

## Dependencies

### Requires
- 001-service-crud.md
