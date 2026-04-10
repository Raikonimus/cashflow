---
id: 005-rbac-middleware
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 005-rbac-middleware

## User Story

**As a** system
**I want** to enforce role-based access control on every API endpoint
**So that** no user can access resources beyond their assigned role and mandant

## Acceptance Criteria

- [ ] **Given** missing/invalid JWT, **When** any protected endpoint, **Then** 401
- [ ] **Given** Viewer role, **When** any POST/PATCH/DELETE endpoint, **Then** 403
- [ ] **Given** Accountant, **When** admin-only endpoint, **Then** 403
- [ ] **Given** valid JWT with mandant_id, **When** accessing another mandant's resource, **Then** 403
- [ ] **Given** Admin role, **When** any endpoint without mandant restriction, **Then** passes

## Technical Notes

- FastAPI Dependency injection: `Depends(require_role("accountant"))`, `Depends(require_mandant_access)`
- All protected routes use these dependencies

## Dependencies

### Requires
- 001-login-jwt.md
