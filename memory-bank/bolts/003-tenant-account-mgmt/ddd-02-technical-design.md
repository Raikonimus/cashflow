---
stage: technical-design
bolt: 003-tenant-account-mgmt
created: 2026-04-06T00:00:00Z
---

# Technical Design: Tenants & Accounts (Bolt 003)

## API-Endpunkte

### Mandant-Verwaltung

| Method | Path | Role | Beschreibung |
|--------|------|------|-------------|
| GET | `/api/v1/mandants` | admin | Alle Mandanten auflisten |
| POST | `/api/v1/mandants` | admin | Neuen Mandanten anlegen |
| GET | `/api/v1/mandants/{mandant_id}` | admin | Mandant-Details |
| PATCH | `/api/v1/mandants/{mandant_id}` | admin | Mandant umbenennen |
| POST | `/api/v1/mandants/{mandant_id}/deactivate` | admin | Mandant deaktivieren |

### Account-Verwaltung

| Method | Path | Role | Beschreibung |
|--------|------|------|-------------|
| GET | `/api/v1/mandants/{mandant_id}/accounts` | accountant+ | Alle Accounts eines Mandanten |
| POST | `/api/v1/mandants/{mandant_id}/accounts` | accountant+ | Neuen Account anlegen |
| GET | `/api/v1/mandants/{mandant_id}/accounts/{account_id}` | accountant+ | Account-Details |
| PATCH | `/api/v1/mandants/{mandant_id}/accounts/{account_id}` | accountant+ | Account aktualisieren |
| GET | `/api/v1/mandants/{mandant_id}/accounts/{account_id}/column-mapping` | accountant+ | Mapping-Config lesen |
| PUT | `/api/v1/mandants/{mandant_id}/accounts/{account_id}/column-mapping` | accountant+ | Mapping-Config speichern (UPSERT) |
| POST | `/api/v1/mandants/{mandant_id}/accounts/{account_id}/remap` | accountant+ | Remapping auslösen |

---

## Datenbankschema

### Erweiterung der `mandants`-Tabelle

Die bestehende Stub-Tabelle aus Migration 001 wird durch eine neue Migration erweitert:

```sql
-- Migration 003: extend mandants, add accounts, column_mapping_configs
ALTER TABLE mandants
    ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT NOW();

CREATE TABLE accounts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mandant_id  UUID NOT NULL REFERENCES mandants(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    iban        VARCHAR(34) UNIQUE,
    currency    VARCHAR(3) NOT NULL DEFAULT 'EUR',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_accounts_mandant_id ON accounts(mandant_id);

CREATE TABLE column_mapping_configs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id        UUID NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
    valuta_date_col   VARCHAR(100) NOT NULL,
    booking_date_col  VARCHAR(100) NOT NULL,
    amount_col        VARCHAR(100) NOT NULL,
    partner_iban_col  VARCHAR(100),
    partner_name_col  VARCHAR(100),
    description_col   VARCHAR(100),
    decimal_separator VARCHAR(1) NOT NULL DEFAULT ',',
    date_format       VARCHAR(50) NOT NULL DEFAULT '%d.%m.%Y',
    encoding          VARCHAR(20) NOT NULL DEFAULT 'utf-8',
    delimiter         VARCHAR(5) NOT NULL DEFAULT ';',
    skip_rows         INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## SQLModel-Modelle

### Erweiterung `Mandant`

```python
# backend/app/tenants/models.py
class Mandant(SQLModel, table=True):
    __tablename__ = "mandants"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    users: list["MandantUser"] = Relationship(back_populates="mandant")
    accounts: list["Account"] = Relationship(back_populates="mandant")
```

### `Account`

```python
class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    name: str = Field(max_length=255)
    iban: str | None = Field(default=None, max_length=34, unique=True, nullable=True)
    currency: str = Field(max_length=3, default="EUR")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    mandant: Mandant = Relationship(back_populates="accounts")
    column_mapping: "ColumnMappingConfig | None" = Relationship(back_populates="account")
```

### `ColumnMappingConfig`

```python
class ColumnMappingConfig(SQLModel, table=True):
    __tablename__ = "column_mapping_configs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", unique=True)
    valuta_date_col: str = Field(max_length=100)
    booking_date_col: str = Field(max_length=100)
    amount_col: str = Field(max_length=100)
    partner_iban_col: str | None = Field(default=None, max_length=100)
    partner_name_col: str | None = Field(default=None, max_length=100)
    description_col: str | None = Field(default=None, max_length=100)
    decimal_separator: str = Field(max_length=1, default=",")
    date_format: str = Field(default="%d.%m.%Y")
    encoding: str = Field(max_length=20, default="utf-8")
    delimiter: str = Field(max_length=5, default=";")
    skip_rows: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    account: Account = Relationship(back_populates="column_mapping")
```

---

## Schemas (Pydantic)

```python
# Mandant
class CreateMandantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

class UpdateMandantRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)

class MandantResponse(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

# Account
class CreateAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    iban: str | None = None
    currency: str = Field(default="EUR", max_length=3)

class UpdateAccountRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    iban: str | None = None
    is_active: bool | None = None

class AccountResponse(BaseModel):
    id: UUID
    mandant_id: UUID
    name: str
    iban: str | None
    currency: str
    is_active: bool
    created_at: datetime
    has_column_mapping: bool   # computed field

# ColumnMappingConfig
class ColumnMappingRequest(BaseModel):
    valuta_date_col: str
    booking_date_col: str
    amount_col: str
    partner_iban_col: str | None = None
    partner_name_col: str | None = None
    description_col: str | None = None
    decimal_separator: str = Field(default=",", max_length=1)
    date_format: str = Field(default="%d.%m.%Y")
    encoding: str = Field(default="utf-8", max_length=20)
    delimiter: str = Field(default=";", max_length=5)
    skip_rows: int = Field(default=0, ge=0)

class ColumnMappingResponse(ColumnMappingRequest):
    id: UUID
    account_id: UUID
    created_at: datetime
    updated_at: datetime

# Remapping
class RemappingTriggerResponse(BaseModel):
    message: str
    account_id: UUID
```

---

## Service-Schicht

### `MandantService`

```python
class MandantService:
    async def list_mandants(self, session: AsyncSession) -> list[Mandant]: ...
    async def get_mandant(self, session: AsyncSession, mandant_id: UUID) -> Mandant: ...
    async def create_mandant(self, session: AsyncSession, data: CreateMandantRequest) -> Mandant: ...
    async def update_mandant(self, session: AsyncSession, mandant_id: UUID, data: UpdateMandantRequest) -> Mandant: ...
    async def deactivate_mandant(self, session: AsyncSession, mandant_id: UUID) -> None:
        # setzt mandant.is_active = False
        # setzt alle accounts.is_active = False (CASCADE im Service, nicht nur DB)
```

### `AccountService`

```python
class AccountService:
    async def list_accounts(self, session: AsyncSession, mandant_id: UUID) -> list[Account]: ...
    async def get_account(self, session: AsyncSession, account_id: UUID, mandant_id: UUID) -> Account: ...
    async def create_account(self, session: AsyncSession, mandant_id: UUID, data: CreateAccountRequest) -> Account:
        # IBAN-Uniqueness-Check (global)
    async def update_account(self, session: AsyncSession, account_id: UUID, data: UpdateAccountRequest) -> Account: ...
    async def get_column_mapping(self, session: AsyncSession, account_id: UUID) -> ColumnMappingConfig | None: ...
    async def set_column_mapping(self, session: AsyncSession, account_id: UUID, data: ColumnMappingRequest) -> ColumnMappingConfig:
        # UPSERT: update wenn vorhanden, sonst insert
    async def trigger_remapping(self, session: AsyncSession, account_id: UUID, actor_id: UUID) -> None:
        # Placeholder: in echten Bolts wird hier ein Job-Queue-Eintrag erstellt
        # Für jetzt: Log-Eintrag + 202 Accepted zurückgeben
```

---

## Modulstruktur

```
backend/app/
├── tenants/
│   ├── __init__.py
│   ├── models.py         # Mandant (vollständig), Account, ColumnMappingConfig
│   ├── schemas.py        # Request/Response Schemas
│   ├── service.py        # MandantService, AccountService
│   └── router.py         # mandants_router, accounts_router
```

**Hinweis:** Das `Mandant`-Model wird von `backend/app/auth/models.py` in `backend/app/tenants/models.py` verschoben, Auth importiert es dann von dort.

---

## Fehlerbehandlung

| Szenario | HTTP-Status | Detail |
|----------|-------------|--------|
| Mandant nicht gefunden | 404 | `"Mandant not found"` |
| Account nicht gefunden | 404 | `"Account not found"` |
| Account gehört nicht zu Mandant | 404 | `"Account not found"` (kein Information-Leak) |
| IBAN bereits belegt | 409 | `"IBAN already in use"` |
| Kein Mandant-Zugriff | 403 | `"Access denied"` |
| Nicht Admin für Mandant-Ops | 403 | `"Admin role required"` |

---

## Migrations-Strategie

Neue Datei: `backend/alembic/versions/003_add_accounts_and_mappings.py`

1. `ALTER TABLE mandants ADD COLUMN updated_at` 
2. `CREATE TABLE accounts`
3. `CREATE TABLE column_mapping_configs`

Down-Migration: Tabellen droppen, Spalte entfernen.

---

## Integration mit Auth

- `require_role("admin")` aus `auth/dependencies.py` für Mandant-CRUD
- `require_mandant_access` für Account-Operationen (User muss zum Mandanten gehören)
- `Mandant`-Model wird in `tenants/models.py` definiert; `auth/models.py` importiert es von dort

---

## Offene Entscheidungen (ADR-Kandidaten)

| Frage | Tendenz |
|-------|---------|
| Mandant-Deaktivierung: Hard cascade auf Accounts oder soft? | Soft (is_active=False) — Daten bleiben, nur Zugriff gesperrt |
| Remapping: Synchron oder Async (Job Queue)? | Async — 202 Accepted; echte Queue-Implementierung in späterem Bolt |
| IBAN Validierung: Format-Check oder nur Uniqueness? | Nur Uniqueness + Normalisierung im MVP; Format-Validierung optional |
