---
unit: 001-identity-access
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-06T00:00:00Z
---

# Unit Brief: identity-access

## Purpose

Authentifizierung, User-Verwaltung und mandantenbasierte Zugriffskontrolle. Diese Unit stellt die Sicherheitsinfrastruktur bereit, auf der alle anderen Units aufbauen.

## Scope

### In Scope
- JWT-basierter Login / Logout
- Passwort-Reset via E-Mail
- Mandantenauswahl bei Multi-Mandanten-Usern
- User-CRUD (Admin, Mandant-Admin)
- Rollen-Verwaltung (admin, mandant_admin, accountant, viewer)
- Mandant-User-Zuweisungen
- RBAC-Middleware (Guards für alle Endpunkte)
- Audit-Log-Einträge für Auth-Ereignisse und User-Änderungen

### Out of Scope
- OAuth / Social Login
- MFA (kann später ergänzt werden)
- Mandanten-Verwaltung (→ 002-tenant-account-mgmt)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Authentifizierung & Session-Management | Must |
| FR-2 | Benutzerverwaltung mit rollenbasiertem Zugriff | Must |
| FR-11 | Audit-Log (Auth-Ereignisse, User-Aktionen) | Must |

---

## Domain Concepts

### Key Entities
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| User | Systemnutzer | id, email, password_hash (nullable), role, is_active |
| UserInvitation | Einladungs-Token | id, user_id, token_hash, expires_at, accepted_at |
| Mandant | Unternehmen/Tenant | id, name (aus 002 referenziert) |
| MandantUser | Zuweisung User ↔ Mandant | mandant_id, user_id |
| AuditLog | Unveränderliche Aktionshistorie | user_id, action, entity_type, old/new_value |

### Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| login | Prüft Credentials, gibt JWT aus | email, password | JWT token, mandant list |
| select_mandant | Setzt aktiven Mandanten in Session | mandant_id | JWT mit mandant_id claim |
| request_password_reset | Sendet Reset-Link per Mail | email | – (fire & forget) |
| reset_password | Setzt neues Passwort via Reset-Token | token, new_password | – |
| create_user | Legt neuen User an + sendet Einladungsmail | email, role, mandant_ids | User |
| send_invitation | Erstellt Token, versendet Einladungsmail | user_id | – |
| accept_invitation | Setzt initiales Passwort, invalidiert Token | token, password | – |
| resend_invitation | Neue Einladung senden, alte invalidieren | user_id | – |
| assign_mandant | Weist User einem Mandanten zu | user_id, mandant_id | – |
| check_permission | RBAC-Guard | user, required_role, mandant_id | allow/deny |

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 7 |
| Must Have | 7 |
| Should Have | 0 |
| Could Have | 0 |

### Stories
- 001-login-jwt.md
- 002-password-reset.md
- 003-user-crud.md
- 004-mandant-user-assignment.md
- 005-rbac-middleware.md
- 006-user-invitation.md
- 007-dev-seed.md
