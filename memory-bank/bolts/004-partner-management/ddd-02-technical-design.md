---
stage: technical-design
bolt: 004-partner-management
created: 2026-04-06T00:00:00Z
---

# Technical Design: Partner Core (Bolt 004)

## API-Endpunkte

| Method | Path | Role | Beschreibung |
|--------|------|------|-------------|
| GET | `/api/v1/mandants/{mandant_id}/partners` | viewer+ | Paginierte Partner-Liste |
| POST | `/api/v1/mandants/{mandant_id}/partners` | accountant+ | Partner anlegen |
| GET | `/api/v1/mandants/{mandant_id}/partners/{partner_id}` | viewer+ | Partner-Details (inkl. IBANs, Namen, Patterns) |
| POST | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/ibans` | accountant+ | IBAN hinzufügen |
| DELETE | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/ibans/{iban_id}` | accountant+ | IBAN entfernen |
| POST | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/names` | accountant+ | Namensvariante hinzufügen |
| DELETE | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/names/{name_id}` | accountant+ | Namensvariante entfernen |
| GET | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/patterns` | viewer+ | Patterns auflisten |
| POST | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/patterns` | accountant+ | Pattern hinzufügen |
| DELETE | `/api/v1/mandants/{mandant_id}/partners/{partner_id}/patterns/{pattern_id}` | accountant+ | Pattern löschen |

---

## Datenbankschema

```sql
-- Migration 004: partner management
CREATE TABLE partners (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mandant_id  UUID NOT NULL REFERENCES mandants(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (mandant_id, name)
);

CREATE INDEX idx_partners_mandant_id ON partners(mandant_id);

CREATE TABLE partner_ibans (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id  UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    iban        VARCHAR(34) NOT NULL UNIQUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_partner_ibans_partner_id ON partner_ibans(partner_id);

CREATE TABLE partner_names (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id  UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (partner_id, name)
);

CREATE INDEX idx_partner_names_partner_id ON partner_names(partner_id);

CREATE TABLE partner_patterns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id   UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    pattern      VARCHAR(500) NOT NULL,
    pattern_type VARCHAR(10) NOT NULL CHECK (pattern_type IN ('string', 'regex')),
    match_field  VARCHAR(20) NOT NULL CHECK (match_field IN ('description', 'partner_name', 'partner_iban')),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (partner_id, pattern, match_field)
);

CREATE INDEX idx_partner_patterns_partner_id ON partner_patterns(partner_id);
```

---

## SQLModel-Modelle

```python
# backend/app/partners/models.py

class Partner(SQLModel, table=True):
    __tablename__ = "partners"
    __table_args__ = (UniqueConstraint("mandant_id", "name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    name: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    ibans: list["PartnerIban"] = Relationship(back_populates="partner")
    names: list["PartnerName"] = Relationship(back_populates="partner")
    patterns: list["PartnerPattern"] = Relationship(back_populates="partner")


class PartnerIban(SQLModel, table=True):
    __tablename__ = "partner_ibans"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    iban: str = Field(max_length=34, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    partner: Partner = Relationship(back_populates="ibans")


class PartnerName(SQLModel, table=True):
    __tablename__ = "partner_names"
    __table_args__ = (UniqueConstraint("partner_id", "name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    name: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    partner: Partner = Relationship(back_populates="names")


class PartnerPatternType(str, Enum):
    string = "string"
    regex = "regex"


class MatchField(str, Enum):
    description = "description"
    partner_name = "partner_name"
    partner_iban = "partner_iban"


class PartnerPattern(SQLModel, table=True):
    __tablename__ = "partner_patterns"
    __table_args__ = (UniqueConstraint("partner_id", "pattern", "match_field"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    pattern: str = Field(max_length=500)
    pattern_type: PartnerPatternType
    match_field: MatchField
    created_at: datetime = Field(default_factory=datetime.utcnow)

    partner: Partner = Relationship(back_populates="patterns")
```

---

## Schemas (Pydantic)

```python
# Partner
class CreatePartnerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    iban: str | None = None        # optionale Erst-IBAN

class PartnerListItem(BaseModel):
    id: UUID
    name: str
    is_active: bool
    iban_count: int
    name_count: int
    pattern_count: int
    created_at: datetime

class PartnerDetailResponse(BaseModel):
    id: UUID
    mandant_id: UUID
    name: str
    is_active: bool
    ibans: list[PartnerIbanResponse]
    names: list[PartnerNameResponse]
    patterns: list[PartnerPatternResponse]
    created_at: datetime
    updated_at: datetime

class PaginatedPartnersResponse(BaseModel):
    items: list[PartnerListItem]
    total: int
    page: int
    size: int
    pages: int

# IBAN
class AddIbanRequest(BaseModel):
    iban: str = Field(min_length=15, max_length=34)

class PartnerIbanResponse(BaseModel):
    id: UUID
    iban: str
    created_at: datetime

# Name
class AddNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

class PartnerNameResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime

# Pattern
class AddPatternRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    pattern_type: PartnerPatternType
    match_field: MatchField

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, v: str, info: FieldValidationInfo) -> str:
        # Wird im Service geprüft (Typ erst nach Parsing bekannt)
        return v

class PartnerPatternResponse(BaseModel):
    id: UUID
    pattern: str
    pattern_type: PartnerPatternType
    match_field: MatchField
    created_at: datetime
```

---

## Service-Schicht

### `PartnerService`

```python
class PartnerService:
    async def list_partners(
        self, session: AsyncSession, mandant_id: UUID, page: int = 1, size: int = 20
    ) -> tuple[list[Partner], int]:
        # Joined subquery für Counts (ibans, names, patterns)

    async def get_partner(
        self, session: AsyncSession, partner_id: UUID, mandant_id: UUID
    ) -> Partner:
        # Lädt mit allen Relationships; 404 wenn nicht gefunden oder falsche mandant_id

    async def create_partner(
        self, session: AsyncSession, mandant_id: UUID, data: CreatePartnerRequest
    ) -> Partner:
        # 409 wenn name+mandant_id bereits existiert
        # Wenn iban angegeben: sofort PartnerIban erstellen

    async def add_iban(
        self, session: AsyncSession, partner_id: UUID, mandant_id: UUID, iban: str
    ) -> PartnerIban:
        # Normalisierung: strip + upper
        # 409 wenn IBAN bereits in partner_ibans (global)

    async def remove_iban(
        self, session: AsyncSession, iban_id: UUID, partner_id: UUID
    ) -> None:
        # 404 wenn nicht gefunden oder falscher Partner

    async def add_name(
        self, session: AsyncSession, partner_id: UUID, mandant_id: UUID, name: str
    ) -> PartnerName:
        # 409 wenn name bereits für denselben Partner vorhanden

    async def remove_name(
        self, session: AsyncSession, name_id: UUID, partner_id: UUID
    ) -> None: ...

    async def add_pattern(
        self, session: AsyncSession, partner_id: UUID, mandant_id: UUID,
        data: AddPatternRequest
    ) -> PartnerPattern:
        # Bei pattern_type=regex: re.compile(data.pattern) → HTTPException 422 bei Fehler
        # 409 wenn gleicher pattern+match_field Kombination für denselben Partner

    async def delete_pattern(
        self, session: AsyncSession, pattern_id: UUID, partner_id: UUID
    ) -> None: ...
```

---

## IBAN-Normalisierung

```python
def normalize_iban(iban: str) -> str:
    """Entfernt Leerzeichen, konvertiert zu Großbuchstaben."""
    return iban.replace(" ", "").upper()
```

Wird vor jedem IBAN-Speichern und vor Uniqueness-Check aufgerufen.

---

## Regex-Validierung

```python
import re

def validate_regex_pattern(pattern: str) -> None:
    """Wirft ValueError wenn pattern kein gültiger Regex ist."""
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}") from e
```

Im Service → `raise HTTPException(status_code=422, detail=f"Invalid regex: {e}")`.

---

## Modulstruktur

```
backend/app/
├── partners/
│   ├── __init__.py
│   ├── models.py        # Partner, PartnerIban, PartnerName, PartnerPattern
│   ├── schemas.py       # alle Request/Response-Schemas
│   ├── service.py       # PartnerService
│   └── router.py        # partners_router (nested unter mandants)
```

---

## Fehlerbehandlung

| Szenario | HTTP | Detail |
|----------|------|--------|
| Partner nicht gefunden / falscher Mandant | 404 | `"Partner not found"` |
| Partner-Name bereits vergeben (gleicher Mandant) | 409 | `"Partner with this name already exists"` |
| IBAN bereits einem anderen Partner zugeordnet | 409 | `"IBAN already assigned to another partner"` |
| Namensvariante bereits vorhanden (gleicher Partner) | 409 | `"Name variant already exists for this partner"` |
| Ungültiger Regex | 422 | `"Invalid regex pattern: {detail}"` |
| Viewer versucht zu schreiben | 403 | `"Insufficient permissions"` |

---

## Migrations-Datei

`backend/alembic/versions/004_add_partners.py`

Erstellt: `partners`, `partner_ibans`, `partner_names`, `partner_patterns` mit allen Constraints und Indizes.

---

## Offene Entscheidungen (ADR-Kandidaten)

| Frage | Tendenz |
|-------|---------|
| IBAN global unique oder nur pro Mandant? | **Global** — eine IBAN gehört immer exakt einem realen Konto, Zuordnung zu mehreren Mandant-Partnern wäre Datenfehler |
| Pagination default page size | 20 (konfigurierbar, max 100) |
| Pattern-Duplikat-Erkennung | Exact-match auf `(partner_id, pattern, match_field)` — kein semantischer Vergleich |
