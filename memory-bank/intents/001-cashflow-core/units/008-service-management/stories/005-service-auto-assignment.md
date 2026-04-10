---
id: 005-service-auto-assignment
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 005-service-auto-assignment

## User Story

**As a** system
**I want** to auto-assign a service for each partner-matched journal line
**So that** bookings are classified without manual work unless ambiguity occurs

## Acceptance Criteria

- [ ] **Given** a journal line and its partner, **When** auto-assignment runs, **Then** only services of that partner are considered
- [ ] **Given** a service outside its validity period, **When** booking_date is checked, **Then** that service is excluded
- [ ] **Given** exactly one matching non-base service, **When** matching completes, **Then** that service is assigned and `service_assignment_mode = auto`
- [ ] **Given** no matching service, **When** matching completes, **Then** the partner's base service is assigned
- [ ] **Given** multiple matching services, **When** matching completes, **Then** the base service is assigned and a `service_assignment` review item is created

## Dependencies

### Requires
- 001-service-crud.md
- 002-service-matchers.md
- 003-base-service-protection.md
- 004-import-pipeline/003-partner-matching.md
