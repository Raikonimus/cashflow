---
id: 006-user-invitation
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 006-user-invitation

## User Story

**As an** Admin or Mandant-Admin
**I want** a newly created user to receive an invitation email with a time-limited link
**So that** the user can set their own initial password securely without the admin knowing it

## Acceptance Criteria

- [ ] **Given** new user created via POST /users, **When** saved, **Then** invitation email is sent automatically; user has no password yet (`password_hash = null`)
- [ ] **Given** valid invitation token (within expiry), **When** POST /auth/accept-invitation { token, password }, **Then** password is set and token invalidated; user can now log in
- [ ] **Given** expired invitation token, **When** POST /auth/accept-invitation, **Then** 400 with message "invitation expired"
- [ ] **Given** already accepted invitation, **When** token reused, **Then** 400 with message "invitation already used"
- [ ] **Given** user with pending invitation, **When** login attempt before accepting, **Then** 401 with message "invitation pending"
- [ ] **Given** Admin/Mandant-Admin, **When** GET /users/:id, **Then** includes `invitation_status: pending|accepted`
- [ ] **Given** Admin/Mandant-Admin, **When** POST /users/:id/resend-invitation, **Then** new invitation sent, old token invalidated
- [ ] Invitation expiry configurable via env var `INVITATION_EXPIRE_DAYS` (default: 7)

## Technical Notes

- Invitation token: signed JWT or random secure token stored in DB (single-use)
- Token stored in a `user_invitations` table: `user_id, token_hash, expires_at, accepted_at`
- Password field nullable until invitation accepted
- Email template: `Hallo {name}, du wurdest eingeladen... [Link gültig bis {date}]`

## Dependencies

### Requires
- 001-login-jwt.md (User entity)
- 003-user-crud.md (user creation triggers invitation)

### Enables
- 005-rbac-middleware.md (user must have accepted invitation to get valid JWT)

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| E-Mail nicht zustellbar (SMTP-Fehler) | User wird angelegt, Fehler geloggt; Admin kann Einladung manuell erneut senden |
| Einladung abgelaufen | Admin muss `resend-invitation` aufrufen |
| User-E-Mail nach Einladung geändert | Neue Einladung senden (alte invalidieren) |
