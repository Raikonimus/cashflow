---
id: 001-mandant-crud
unit: 002-tenant-account-mgmt
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-mandant-crud

## User Story

**As an** Admin
**I want** to create, edit, and deactivate mandants
**So that** I can manage the companies using the system

## Acceptance Criteria

- [ ] **Given** Admin, **When** POST /mandants, **Then** mandant is created with name
- [ ] **Given** Admin, **When** PATCH /mandants/:id, **Then** name can be updated
- [ ] **Given** Admin, **When** deactivate mandant, **Then** all associated users lose access
- [ ] **Given** non-Admin, **When** POST /mandants, **Then** 403

## Dependencies

### Requires
- 001-identity-access/005-rbac-middleware.md
