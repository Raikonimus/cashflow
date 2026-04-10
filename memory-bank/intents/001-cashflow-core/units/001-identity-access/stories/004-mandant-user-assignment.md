---
id: 004-mandant-user-assignment
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-mandant-user-assignment

## User Story

**As an** Admin
**I want** to assign users to mandants
**So that** non-admin users can only access their designated mandants

## Acceptance Criteria

- [ ] **Given** Admin, **When** POST /mandants/:id/users, **Then** user is assigned to mandant
- [ ] **Given** Admin, **When** DELETE /mandants/:id/users/:uid, **Then** assignment is removed
- [ ] **Given** User assigned to mandant_A only, **When** request with mandant_B in JWT, **Then** 403
- [ ] **Given** Admin role, **When** any request, **Then** passes mandant check regardless of explicit assignments

## Dependencies

### Requires
- 001-login-jwt.md
- 005-rbac-middleware.md
