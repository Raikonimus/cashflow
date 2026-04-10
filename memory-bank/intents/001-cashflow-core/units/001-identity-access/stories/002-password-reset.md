---
id: 002-password-reset
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-password-reset

## User Story

**As a** user who forgot their password
**I want** to receive a reset link by email
**So that** I can set a new password and regain access

## Acceptance Criteria

- [ ] **Given** known email, **When** POST /auth/forgot-password, **Then** reset email is sent within 30 s; always returns 200 (no email enumeration)
- [ ] **Given** valid reset token (< 1 h old), **When** POST /auth/reset-password, **Then** password is updated and token invalidated
- [ ] **Given** expired or invalid token, **When** POST /auth/reset-password, **Then** returns 400
- [ ] **Given** successful reset, **When** user logs in with new password, **Then** login succeeds

## Technical Notes

- Token: signed JWT with short expiry (1 h), stored in DB for single-use invalidation
- Email: SMTP via env vars (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS)

## Dependencies

### Requires
- 001-login-jwt.md (User entity exists)
