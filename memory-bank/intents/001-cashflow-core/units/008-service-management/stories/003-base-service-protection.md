---
id: 003-base-service-protection
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-base-service-protection

## User Story

**As a** system
**I want** every partner to always have exactly one protected base service
**So that** service assignment always has a safe fallback

## Acceptance Criteria

- [ ] **Given** a new partner is created, **When** creation completes, **Then** exactly one base service is created automatically for that partner
- [ ] **Given** a base service, **When** its name is changed, **Then** 422
- [ ] **Given** a base service, **When** delete is requested, **Then** 409
- [ ] **Given** a base service, **When** matcher CRUD is requested, **Then** 422
- [ ] **Given** a partner already has a base service, **When** another base service would be created, **Then** the operation is rejected by application and database constraints

## Dependencies

### Requires
- 003-partner-management/001-partner-crud.md
