---
id: 002-service-matchers
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-service-matchers

## User Story

**As an** Accountant
**I want** to maintain string and regex matchers for a service
**So that** future journal lines can be auto-assigned correctly

## Acceptance Criteria

- [ ] **Given** a non-base service, **When** POST /services/:id/matchers { pattern, pattern_type }, **Then** a matcher is created
- [ ] **Given** `pattern_type = regex`, **When** the pattern is invalid, **Then** save is rejected with 422 and validation details
- [ ] **Given** a matcher exists, **When** PATCH or DELETE is called, **Then** the matcher is updated or removed and partner revalidation is triggered
- [ ] **Given** `pattern_type = string`, **When** matching executes later, **Then** it behaves as case-insensitive contains
- [ ] **Given** a base service, **When** matcher CRUD is requested, **Then** 422

## Dependencies

### Requires
- 001-service-crud.md
- 003-base-service-protection.md
