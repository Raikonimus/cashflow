---
stage: technical-design
bolt: 001-identity-access
created: 2026-04-06T00:00:00Z
---

# Technical Design: identity-access (Bolt 001 – Auth Foundation)

## Architecture Pattern

**Layered Architecture** (3 Schichten) innerhalb eines Feature-Moduls:

```
backend/app/auth/
├── router.py        ← HTTP-Schicht: FastAPI Endpoints, Request/Response-Models
├── service.py       ← Domänen-Schicht: AuthService, PasswordResetService, RbacService
├── models.py        ← Persistenzschicht: SQLModel Table-Definitionen
├── schemas.py       ← Pydantic I/O-Schemas (keine DB-Abhängigkeit)
├── dependencies.py  ← FastAPI Dependencies: JWT-Guard, RBAC-Guards
└── security.py      ← JwtTokenService, Passwort-Hashing (bcrypt)
```

**Rationale**: Feature-based Struktur (gemäß `coding-standards.md`). Auth ist ein klar abgegrenztes Modul ohne Seiteneffekte auf andere Features. Kein CQRS nötig — die Lese-/Schreib-Trennung ist trivial.

---

## Layer Structure

| Layer | File | Responsibility |
|-------|------|----------------|
| HTTP | `router.py` | Request-Validierung, Response-Serialisierung, HTTP-Status-Codes |
| Domain | `service.py` | Business-Logik, Domain-Events, Orchestrierung |
| Cross-cutting | `dependencies.py` | FastAPI Dependency Injection für Guards |
| Infrastructure | `models.py` | SQLModel-Definitionen, DB-Zugriff via async Session |
| Utilities | `security.py` | JWT, bcrypt — kein Framework-Coupling |

---

## API Contracts

### POST /api/v1/auth/login
```yaml
Request:
  email: string (Email)
  password: string

Response 200:
  access_token: string (JWT)
  token_type: "bearer"
  mandants: [{id: UUID, name: string}]  # leer wenn Admin
  requires_mandant_selection: boolean   # true wenn > 1 Mandant

Response 401:
  detail: "Invalid credentials" | "Account disabled" | "Invitation pending"
```

### POST /api/v1/auth/select-mandant
```yaml
Request:
  mandant_id: UUID

Response 200:
  access_token: string (JWT mit mandant_id claim)
  token_type: "bearer"

Response 403:
  detail: "Access to mandant denied"
```

### POST /api/v1/auth/forgot-password
```yaml
Request:
  email: string (Email)

Response 200:
  message: "If this email exists, a reset link has been sent"
  # Immer 200 — kein E-Mail-Enumeration
```

### POST /api/v1/auth/reset-password
```yaml
Request:
  token: string
  password: string (min 8 Zeichen)

Response 200:
  message: "Password updated successfully"

Response 400:
  detail: "Token expired" | "Token already used" | "Invalid token"
```

### GET /api/v1/auth/me
```yaml
Headers:
  Authorization: Bearer {jwt}

Response 200:
  id: UUID
  email: string
  role: UserRole
  mandant_id: UUID|null
  is_active: boolean
```

---

## Data Persistence

### SQLModel Table-Definitionen

```python
# users
class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=254)
    password_hash: str | None = None          # null bis Einladung angenommen
    role: UserRole                             # Enum: admin|mandant_admin|accountant|viewer
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

# mandant_users
class MandantUser(SQLModel, table=True):
    __tablename__ = "mandant_users"
    mandant_id: UUID = Field(foreign_key="mandants.id", primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)

# password_reset_tokens
class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True)       # SHA-256 des raw Tokens
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
```

### Alembic Migration Strategie
- Migrations liegen unter `backend/alembic/versions/`
- Initiale Migration: `001_create_auth_tables.py` erzeugt `users`, `mandant_users`, `password_reset_tokens`
- `mandants`-Tabelle wird in Bolt 003 (Unit 002) migriert; hier nur als FK-Target referenziert

### Datenbankindizes
- `users.email` — UNIQUE INDEX (Login-Lookup)
- `password_reset_tokens.token_hash` — INDEX (Token-Validierung)
- `password_reset_tokens.user_id` — INDEX (Invalidierung aller Token eines Users)

---

## Security Patterns

### JWT
- Algorithmus: HS256
- Secret: `JWT_SECRET_KEY` (Env-Variable, min. 32 Zeichen, kein Default in Code)
- Ablauf: `JWT_EXPIRE_MINUTES` (Default: 60)
- Payload: `{ "sub": user_id, "role": role, "mandant_id": null|uuid, "exp": unix_ts }`
- Kein Refresh-Token in diesem Bolt (kann später ergänzt werden)

### Passwort-Hashing
- Algorithmus: bcrypt, cost factor 12
- Library: `passlib[bcrypt]`
- Passwort-Mindestlänge: 8 Zeichen (Pydantic-Validierung in Schema)

### Reset-Token
- Raw token: `secrets.token_urlsafe(32)` (URL-safe, 32 Bytes Entropie)
- Gespeichert: SHA-256-Hash des raw Tokens (kein Plain-Text in DB)
- Ablauf: 1 Stunde (`PASSWORD_RESET_EXPIRE_MINUTES=60`)
- Anti-Timing-Attack: Vergleich via `hmac.compare_digest`

### RBAC Guards (FastAPI Dependencies)
```python
# Verwendung:
@router.get("/admin/users", dependencies=[Depends(require_role("mandant_admin"))])

# Hierarchie:
ROLE_HIERARCHY = {
    "admin": 4,
    "mandant_admin": 3,
    "accountant": 2,
    "viewer": 1,
}

def require_role(min_role: str):
    def dependency(current_user = Depends(get_current_user)):
        if ROLE_HIERARCHY[current_user.role] < ROLE_HIERARCHY[min_role]:
            raise HTTPException(status_code=403)
    return dependency

def require_mandant_access(mandant_id: UUID):
    # Admin: immer erlaubt
    # Andere: MandantUser-Eintrag muss existieren
```

### E-Mail-Enumeration Prevention
- `POST /auth/forgot-password` gibt immer HTTP 200 zurück, unabhängig davon ob E-Mail bekannt
- Response-Text ist immer identisch

---

## NFR-Planung

### Performance
- Bcrypt-Operationen sind CPU-intensiv (~100ms bei cost 12) → async-safe via `run_in_executor`
- JWT-Verifizierung: <1ms → kein Caching nötig
- DB-Queries in Auth-Pfad: max. 2 Queries (User-Lookup + MandantUser-Lookup) → Index-covered

### Skalierbarkeit
- JWT ist stateless → horizontales Scaling ohne Session-Store möglich
- Kein serverseitiger Session-State

### Async
- Alle Repository-Methoden: `async def` mit `AsyncSession` (asyncpg)
- Bcrypt: `await asyncio.get_event_loop().run_in_executor(None, bcrypt_hash, password)`

---

## Integration Points

### E-Mail-Service (Passwort-Reset)
- Interface: `EmailService.send_password_reset(to: str, reset_url: str) → None`
- Implementierung: stdlib `smtplib` + `email.mime.multipart.MIMEMultipart` + `email.mime.text.MIMEText` + `email.utils.formataddr`
- Async-Wrapper: `asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(), ...)` — smtplib ist synchron
- Konfiguration:
  - `SMTP_ENABLED` (bool, default: false)
  - `SMTP_HOST`, `SMTP_PORT`
  - `SMTP_SECURITY` (`starttls` | `ssl` | `none`)
  - `SMTP_USERNAME`, `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`
  - `SMTP_REPLY_TO`
- Reset-URL-Format: `{FRONTEND_URL}/reset-password?token={raw_token}`
- Template: Plain-Text + HTML (Inline, kein Template-Engine nötig für MVP)
- Fehlerbehandlung: SMTP-Fehler wird geloggt (structlog), User-Anlage schlägt nicht fehl

### Audit-Log (Domain Events)
- `AuthService` publiziert Events nach DB-Schreiboperation
- Für diesen Bolt: direkter Aufruf `AuditLogService.log(...)` nach jeder relevanten Aktion
- `AuditLogService` wird in Unit 006 (journal-viewer) vollständig implementiert; hier einfaches direktes DB-Insert in `audit_logs`

---

## Datei-/Ordnerstruktur (vollständig)

```
backend/
├── app/
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── router.py          # FastAPI Router, Endpoints
│   │   ├── service.py         # AuthService, PasswordResetService
│   │   ├── models.py          # User, MandantUser, PasswordResetToken (SQLModel)
│   │   ├── schemas.py         # LoginRequest, TokenResponse, ForgotPasswordRequest, ...
│   │   ├── dependencies.py    # get_current_user, require_role, require_mandant_access
│   │   └── security.py        # JwtTokenService, hash_password, verify_password
│   ├── core/
│   │   ├── config.py          # Settings (pydantic-settings, liest .env)
│   │   └── database.py        # AsyncEngine, AsyncSession, get_session Dependency
│   └── main.py                # FastAPI App, Router-Einbindung, CORS
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_create_auth_tables.py
├── tests/
│   └── auth/
│       ├── test_login.py
│       ├── test_password_reset.py
│       └── test_rbac.py
├── .env.example
├── pyproject.toml             # Dependencies, Ruff-Config, pytest-Config
└── README.md
```

---

## Abhängigkeiten (pyproject.toml)

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlmodel>=0.0.21",
    "asyncpg>=0.30",
    "alembic>=1.13",
    "passlib[bcrypt]>=1.7",
    "python-jose[cryptography]>=3.3",   # JWT
    # E-Mail via stdlib smtplib + ThreadPoolExecutor (kein extra Package nötig)
    "pydantic-settings>=2.0",           # .env Laden
    "structlog>=24.0",                  # Strukturiertes Logging
]

[tool.ruff]
select = ["E", "F", "I", "N", "UP"]
line-length = 88

[tool.pytest.ini_options]
asyncio_mode = "auto"
```
