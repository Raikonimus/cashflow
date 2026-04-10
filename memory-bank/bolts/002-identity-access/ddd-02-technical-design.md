---
stage: technical-design
bolt: 002-identity-access
created: 2026-04-06T00:00:00Z
---

# Technical Design: User Management (Bolt 002)

## Architecture Pattern

Erweiterung des bestehenden `app/auth/`-Moduls aus Bolt 001. Neue Endpoints und Services werden in dasselbe Feature-Modul integriert — **kein neues Modul**. Bolt 001 definiert bereits `User`, `MandantUser` und die RBAC-Guards; Bolt 002 baut direkt darauf auf.

```
backend/app/auth/
├── router.py           ← [ERWEITERT] Neue Endpoints: /users, /mandants/:id/users
├── service.py          ← [ERWEITERT] UserManagementService, InvitationService, MandantAssignmentService
├── models.py           ← [ERWEITERT] UserInvitation hinzugefügt
├── schemas.py          ← [ERWEITERT] Create/Update/Response-Schemas
├── dependencies.py     ← [UNVERÄNDERT]
├── security.py         ← [UNVERÄNDERT]
└── email.py            ← [ERWEITERT] send_invitation_email()

backend/app/scripts/
└── seed.py             ← [NEU] Dev-Seed-Script (Story 007)
```

---

## API Contracts

### POST /api/v1/users
```yaml
Auth: Bearer {jwt}  # Admin or Mandant-Admin
Request:
  email: string (Email)
  role: "accountant" | "viewer"   # Mandant-Admin: nur diese 2
          # Admin: zusätzlich "mandant_admin" | "admin" erlaubt

Response 201:
  id: UUID
  email: string
  role: string
  is_active: boolean
  invitation_status: "pending"

Response 400:
  detail: "User with this email already exists"
Response 403:
  detail: "Insufficient permissions to assign this role"
```

### GET /api/v1/users/:id
```yaml
Auth: Bearer {jwt}  # Admin or Mandant-Admin
Response 200:
  id: UUID
  email: string
  role: string
  is_active: boolean
  invitation_status: "pending" | "accepted" | "expired"
Response 403:  # Mandant-Admin requesting user not in their mandant
  detail: "Access denied"
```

### PATCH /api/v1/users/:id
```yaml
Auth: Bearer {jwt}  # Admin or Mandant-Admin
Request:
  email?: string (Email)
  role?: string
  is_active?: boolean

Response 200:
  id: UUID
  email: string
  role: string
  is_active: boolean
  invitation_status: "pending" | "accepted" | "expired"

Response 403:
  detail: "Insufficient permissions" | "Access denied"
```

### POST /api/v1/users/:id/resend-invitation
```yaml
Auth: Bearer {jwt}  # Admin or Mandant-Admin
Response 200:
  message: "Invitation resent"
Response 400:
  detail: "User has already accepted their invitation"
```

### POST /api/v1/auth/accept-invitation
```yaml
# Kein Auth-Header nötig — public endpoint
Request:
  token: string
  password: string (min 8 chars)

Response 200:
  message: "Invitation accepted. You can now log in."

Response 400:
  detail: "Invitation expired" | "Invitation already used" | "Invalid token"
```

### POST /api/v1/mandants/:mandant_id/users
```yaml
Auth: Bearer {jwt}  # Admin only
Request:
  user_id: UUID

Response 201:
  mandant_id: UUID
  user_id: UUID
  created_at: datetime

Response 404:
  detail: "User not found" | "Mandant not found"
Response 409:
  detail: "User already assigned to this mandant"
```

### DELETE /api/v1/mandants/:mandant_id/users/:user_id
```yaml
Auth: Bearer {jwt}  # Admin only
Response 204: (no body)
Response 404:
  detail: "Assignment not found"
```

---

## Data Persistence

### Neue SQLModel-Definition

```python
class UserInvitation(SQLModel, table=True):
    __tablename__ = "user_invitations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True, max_length=64)   # SHA-256 (ADR-003)
    expires_at: datetime
    accepted_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
```

### Alembic Migration
Datei: `alembic/versions/002_add_user_invitations.py`

```sql
CREATE TABLE user_invitations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_user_invitations_user_id ON user_invitations(user_id);
CREATE INDEX ix_user_invitations_token_hash ON user_invitations(token_hash);
```

---

## Rollen-Berechtigungsmatrix

| Operation | Admin | Mandant-Admin | Accountant | Viewer |
|-----------|-------|--------------|------------|--------|
| POST /users (role=admin/mandant_admin) | ✅ | ❌ 403 | ❌ 403 | ❌ 403 |
| POST /users (role=accountant/viewer) | ✅ | ✅ (eigener Mandant) | ❌ | ❌ |
| GET /users/:id | ✅ | ✅ (eigener Mandant) | ❌ 403 | ❌ 403 |
| PATCH /users/:id | ✅ | ✅ (eigener Mandant) | ❌ | ❌ |
| POST /users/:id/resend-invitation | ✅ | ✅ (eigener Mandant) | ❌ | ❌ |
| POST /mandants/:id/users | ✅ | ❌ | ❌ | ❌ |
| DELETE /mandants/:id/users/:uid | ✅ | ❌ | ❌ | ❌ |

**Mandant-Admin-Scope Prüfung:**  
Ein Mandant-Admin darf nur User aus *seinem* Mandanten verwalten. Die Prüfung erfolgt via `MandantUser`-Lookup: Wenn der Target-User nicht im Mandanten des Aufrufers ist → 403.

---

## Security Patterns

### Einladungs-Token
Identisch zu Reset-Token (ADR-003):
- Raw: `secrets.token_urlsafe(32)`
- DB: SHA-256-Hash
- Ablauf: `now() + timedelta(days=INVITATION_EXPIRE_DAYS)` (default: 7)
- Einlösung: `hmac.compare_digest` (timing-safe)

### Rollen-Eskalation verhindern
Mandant-Admin kann sich keine höhere Rolle geben:
```python
ROLES_MANDANT_ADMIN_CAN_CREATE = {UserRole.accountant, UserRole.viewer}
if actor.role == "mandant_admin" and requested_role not in ROLES_MANDANT_ADMIN_CAN_CREATE:
    raise HTTPException(403)
```

### Accept-Invitation — kein Auth-Header
`POST /auth/accept-invitation` ist public (kein `Depends(get_current_user)`). Der Token selbst ist das Credential.

---

## Env-Variablen (Ergänzungen)

```bash
# Einladungs-Token Ablauf (Tage, default 7)
INVITATION_EXPIRE_DAYS=7

# Dev-Seed (nur in .env.example, nie in production)
SEED_ADMIN_EMAIL=admin@local.dev
SEED_ADMIN_PASSWORD=
```

---

## Datei-/Ordnerstruktur (Ergänzungen zu Bolt 001)

```
backend/
├── app/
│   ├── auth/
│   │   ├── models.py       ← + UserInvitation
│   │   ├── schemas.py      ← + CreateUserRequest, UpdateUserRequest,
│   │   │                       UserDetailResponse, AcceptInvitationRequest,
│   │   │                       MandantUserResponse
│   │   ├── service.py      ← + UserManagementService, InvitationService,
│   │   │                       MandantAssignmentService
│   │   ├── router.py       ← + /users, /users/:id, /mandants/:id/users,
│   │   │                       /auth/accept-invitation
│   │   └── email.py        ← + send_invitation_email()
│   └── scripts/
│       ├── __init__.py
│       └── seed.py         ← NEU: python -m app.scripts.seed
├── alembic/
│   └── versions/
│       └── 002_add_user_invitations.py
└── tests/
    └── auth/
        ├── test_user_crud.py
        ├── test_invitation.py
        └── test_seed.py
```

---

## NFR-Planung

- **Idempotenz Seed**: Prüfung via `SELECT ... WHERE email = ?`; kein Fehler wenn bereits vorhanden
- **SMTP-Fehler bei Invitation**: User wird angelegt, Fehler geloggt — kein Rollback (Admin kann `resend-invitation` aufrufen)
- **Async**: alle Service-Methoden `async def`, Repository-Aufrufe via `AsyncSession`
