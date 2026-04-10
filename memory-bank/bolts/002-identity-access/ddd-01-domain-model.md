---
stage: domain-model
bolt: 002-identity-access
created: 2026-04-06T00:00:00Z
---

# Domain Model: User Management (Bolt 002)

## Bounded Context

**User Management** ist ein Sub-Context von *Identity & Access*. Während Bolt 001 die Authentifizierung und den Token-Lebenszyklus modelliert, verantwortet Bolt 002 den gesamten User-Lebenszyklus: Anlage, Zuweisung zu Mandanten, Einladungs-Flow und den Dev-Seed.

---

## Entities

### User *(bereits in Bolt 001 eingeführt — hier erweitert)*

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| email | string | UNIQUE, NOT NULL | max 254 Zeichen |
| password_hash | string\|null | nullable | null bis Einladung angenommen |
| role | UserRole | NOT NULL | admin / mandant_admin / accountant / viewer |
| is_active | bool | default true | Deaktivierung durch Admin |
| created_at | datetime | NOT NULL | |
| updated_at | datetime | NOT NULL | auto-update bei jedem Write |

**Neu in Bolt 002:** Schreiboperationen (create, update, deactivate) auf User durch Admin/Mandant-Admin.

---

### UserInvitation

Repräsentiert eine ausstehende Einladung für einen noch nicht aktiven User.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| user_id | UUID | FK users.id, INDEX | 1:1 pro ausstehende Einladung |
| token_hash | string(64) | INDEX | SHA-256 des raw Tokens (ADR-003) |
| expires_at | datetime | NOT NULL | `created_at + INVITATION_EXPIRE_DAYS` |
| accepted_at | datetime\|null | nullable | null = noch offen |
| created_at | datetime | NOT NULL | |

**Invarianten:**
- Pro User kann es mehrere `UserInvitation`-Einträge geben, aber maximal eine unbenutzte (`accepted_at IS NULL`)
- Ein `resend-invitation` invalidiert alle alten offenen Tokens für diesen User (setzt `accepted_at = now()`)
- Passwort darf erst gesetzt werden, wenn Invitation angenommen

---

### MandantUser *(bereits in Bolt 001 eingeführt — hier mit Schreib-Ops erweitert)*

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| mandant_id | UUID | FK, PK | |
| user_id | UUID | FK, PK | |
| created_at | datetime | NOT NULL | |

**Neu in Bolt 002:** Explizite Endpoints zum Zuweisen und Entfernen von Usern zu Mandanten.

---

## Value Objects

### UserRole *(bereits in Bolt 001)*
`admin | mandant_admin | accountant | viewer`

### InvitationStatus
Berechnetes Value Object — kein eigenes DB-Feld:
- `pending` — `accepted_at IS NULL AND expires_at > now()`
- `expired` — `accepted_at IS NULL AND expires_at <= now()`
- `accepted` — `accepted_at IS NOT NULL`

### CreateUserRequest
- email: Email (valide)
- role: UserRole (eingeschränkt je nach Aufrufer-Rolle)

### AcceptInvitationRequest
- token: string (raw, wird gehasht beim Lookup)
- password: string (min. 8 Zeichen)

---

## Aggregates

### UserAggregate *(erweitert)*
**Root**: `User`
**Enthält**: `UserInvitation` (gehört nur zu diesem User)

**Invarianten:**
- Mandant-Admin darf nur `accountant` oder `viewer` anlegen
- Ein deaktivierter User löst keine neuen Einladungen aus
- Das Setzen des Passworts ist nur über den Invitation-Flow oder den Seed-Script erlaubt (nicht durch PATCH /users/:id)

### MandantUserAggregate
**Root**: `MandantUser`
Einfaches Join-Aggregat; keine eigene Business-Logik über FK-Constraints hinaus.

---

## Domain Services

### UserManagementService
- `create_user(creator: User, data: CreateUserRequest) → User`
  - prüft Rollen-Berechtigung des Aufrufers
  - legt User an (`password_hash = null`)
  - delegiert an `InvitationService.send_invitation(user)`
- `update_user(actor: User, target_id: UUID, patch: dict) → User`
  - prüft Mandant-Zugehörigkeit bei Mandant-Admin
  - verhindert Selbst-Deaktivierung
- `deactivate_user(actor: User, target_id: UUID) → None`
  - setzt `is_active = false`

### InvitationService
- `send_invitation(user: User) → UserInvitation`
  - invalidiert offene Einladungen
  - generiert neuen raw Token (`secrets.token_urlsafe(32)`)
  - speichert `token_hash` in DB
  - sendet Einladungs-E-Mail
- `accept_invitation(raw_token: str, password: str) → None`
  - sucht Einladung via Hash-Lookup
  - prüft `expires_at` und `accepted_at`
  - setzt `user.password_hash = bcrypt(password)`
  - setzt `invitation.accepted_at = now()`
- `resend_invitation(actor: User, user_id: UUID) → None`
  - delegiert an `send_invitation()` (invalidiert alte Tokens implizit)

### MandantAssignmentService
- `assign_user(admin: User, mandant_id: UUID, user_id: UUID) → MandantUser`
- `unassign_user(admin: User, mandant_id: UUID, user_id: UUID) → None`

### DevSeedService
- `seed_admin(email: str, password: str) → None`
  - läuft nur wenn `ENV != production`
  - legt Admin-User an oder überspringt wenn bereits vorhanden
  - setzt `password_hash` direkt (bypasses Invitation Flow — nur im Seed)

---

## Domain Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `UserCreated` | `create_user()` | user_id, email, role, created_by |
| `UserDeactivated` | `deactivate_user()` | user_id, deactivated_by |
| `UserRoleChanged` | `update_user()` mit role-Änderung | user_id, old_role, new_role |
| `InvitationSent` | `send_invitation()` | user_id, expires_at |
| `InvitationAccepted` | `accept_invitation()` | user_id |
| `MandantUserAssigned` | `assign_user()` | mandant_id, user_id |
| `MandantUserUnassigned` | `unassign_user()` | mandant_id, user_id |

---

## Repository Interfaces

```python
class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def list_by_mandant(self, mandant_id: UUID) -> list[User]: ...
    async def save(self, user: User) -> User: ...

class UserInvitationRepository(Protocol):
    async def get_pending_by_token_hash(self, token_hash: str) -> UserInvitation | None: ...
    async def get_pending_by_user_id(self, user_id: UUID) -> UserInvitation | None: ...
    async def invalidate_pending(self, user_id: UUID) -> None: ...
    async def save(self, invitation: UserInvitation) -> UserInvitation: ...

class MandantUserRepository(Protocol):
    async def get(self, mandant_id: UUID, user_id: UUID) -> MandantUser | None: ...
    async def list_by_mandant(self, mandant_id: UUID) -> list[MandantUser]: ...
    async def save(self, mu: MandantUser) -> MandantUser: ...
    async def delete(self, mandant_id: UUID, user_id: UUID) -> None: ...
```

---

## Ubiquitäres Vokabular

| Begriff | Definition |
|---------|-----------|
| **Einladung** | Initialer Zugang-Link der einem neuen User per E-Mail zugestellt wird; einmalig nutzbar |
| **Einladung annehmen** | Das Setzen des eigenen Passworts über den Einladungs-Link |
| **Einladung ablaufen lassen** | Einladung wurde nicht innerhalb von `INVITATION_EXPIRE_DAYS` angenommen |
| **Mandant-Zuweisung** | Explizite Verknüpfung eines Users mit einem Mandanten (nur Admin) |
| **Dev-Seed** | Einmaliges Skript zum Anlegen eines Admin-Users in der lokalen Entwicklungsumgebung |
| **Pending User** | User mit `password_hash = null` — kann sich nicht einloggen |
