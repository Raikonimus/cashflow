---
id: 001-login-jwt
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-login-jwt

## User Story

**As a** registered user
**I want** to log in with my email and password
**So that** I receive a JWT token and can access the system

## Acceptance Criteria

- [ ] **Given** valid credentials, **When** POST /auth/login, **Then** returns JWT token + list of accessible mandants
- [ ] **Given** user has exactly 1 mandant, **When** login succeeds, **Then** JWT contains mandant_id claim directly
- [ ] **Given** user has > 1 mandant, **When** login succeeds, **Then** JWT contains no mandant_id; client calls POST /auth/select-mandant
- [ ] **Given** invalid credentials, **When** POST /auth/login, **Then** returns 401; failure is written to audit_log
- [ ] **Given** deactivated user, **When** POST /auth/login, **Then** returns 401

## Technical Notes

- JWT payload: `{ user_id, role, mandant_id (opt), exp }`
- Token expiry: configurable via `JWT_EXPIRE_MINUTES` env var
- Password hashing: bcrypt
- **Logout**: Client-only — Token wird im Browser gelöscht; keine serverseitige Invalidierung. Token bleibt bis `exp` technisch gültig, was für diesen Use Case akzeptabel ist.

## Dependencies

### Requires
- None

### Enables
- 002-password-reset.md
- 003-user-crud.md
- 005-rbac-middleware.md
