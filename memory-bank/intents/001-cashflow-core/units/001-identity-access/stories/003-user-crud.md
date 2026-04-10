---
id: 003-user-crud
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-user-crud

## User Story

**As an** Admin or Mandant-Admin
**I want** to create, edit, and deactivate users
**So that** I can manage who has access to the system

## Acceptance Criteria

- [ ] **Given** Admin, **When** POST /users, **Then** can create user with any role
- [ ] **Given** Mandant-Admin, **When** POST /users, **Then** can only create accountant or viewer roles; 403 on other roles
- [ ] **Given** Admin, **When** PATCH /users/:id, **Then** can update email, role, is_active
- [ ] **Given** Mandant-Admin, **When** PATCH /users/:id for user not in their mandant, **Then** 403
- [ ] **Given** deactivated user, **When** login attempt, **Then** 401

## Dependencies

### Requires
- 001-login-jwt.md
- 005-rbac-middleware.md
