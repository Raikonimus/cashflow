---
stage: technical-design
bolt: 006-import-core
created: 2026-04-06T00:00:00Z
---

# Technical Design: Import Core (Bolt 006)

## API-Endpunkte

| Method | Path | Role | Beschreibung |
|--------|------|------|-------------|
| POST | `/api/v1/mandants/{mandant_id}/accounts/{account_id}/imports` | accountant+ | Eine oder mehrere CSV-Dateien hochladen |
| GET | `/api/v1/mandants/{mandant_id}/accounts/{account_id}/imports` | viewer+ | Import-Runs für Account auflisten |
| GET | `/api/v1/mandants/{mandant_id}/accounts/{account_id}/imports/{run_id}` | viewer+ | Import-Run Details |

---

## Datenbankschema

```sql
-- Migration 006: import_runs + journal_lines

CREATE TYPE import_status AS ENUM ('pending', 'processing', 'completed', 'failed');

CREATE TABLE import_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    mandant_id      UUID NOT NULL REFERENCES mandants(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),
    filename        VARCHAR(255) NOT NULL,
    row_count       INTEGER NOT NULL DEFAULT 0,
    skipped_count   INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    status          import_status NOT NULL DEFAULT 'pending',
    error_details   JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_import_runs_account_id ON import_runs(account_id);
CREATE INDEX idx_import_runs_mandant_id ON import_runs(mandant_id);
CREATE INDEX idx_import_runs_created_at ON import_runs(created_at DESC);

CREATE TABLE journal_lines (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    import_run_id       UUID NOT NULL REFERENCES import_runs(id),
    partner_id          UUID REFERENCES partners(id),      -- NULL bis Matching (Bolt 007)
    valuta_date         DATE NOT NULL,
    booking_date        DATE NOT NULL,
    amount              NUMERIC(15,2) NOT NULL,
    currency            VARCHAR(3) NOT NULL DEFAULT 'EUR',
    text                VARCHAR(1000),
    partner_name_raw    VARCHAR(500),
    partner_iban_raw    VARCHAR(34),
    unmapped_data       JSONB,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_journal_lines_account_id ON journal_lines(account_id);
CREATE INDEX idx_journal_lines_import_run_id ON journal_lines(import_run_id);
CREATE INDEX idx_journal_lines_partner_id ON journal_lines(partner_id);

-- Dubletten-Constraint (NULL-safe: COALESCE für nullable Felder)
CREATE UNIQUE INDEX idx_journal_lines_dedup ON journal_lines (
    account_id,
    valuta_date,
    booking_date,
    amount,
    COALESCE(partner_iban_raw, ''),
    COALESCE(partner_name_raw, '')
);
```

---

## SQLModel-Modelle

```python
# backend/app/imports/models.py

from enum import Enum as PyEnum
from uuid import UUID, uuid4
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Enum, JSONB, Numeric, UniqueConstraint, Index
from sqlmodel import SQLModel, Field, Relationship


class ImportStatus(str, PyEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ImportRun(SQLModel, table=True):
    __tablename__ = "import_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    user_id: UUID = Field(foreign_key="users.id")
    filename: str = Field(max_length=255)
    row_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    error_count: int = Field(default=0)
    status: ImportStatus = Field(
        default=ImportStatus.pending,
        sa_column=Column(Enum(ImportStatus), nullable=False),
    )
    error_details: list | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)

    lines: list["JournalLine"] = Relationship(back_populates="import_run")


class JournalLine(SQLModel, table=True):
    __tablename__ = "journal_lines"
    __table_args__ = (
        Index(
            "idx_journal_lines_dedup",
            "account_id", "valuta_date", "booking_date", "amount",
            "partner_iban_raw", "partner_name_raw",
            unique=True,
            postgresql_where=None,  # COALESCE handled in raw migration
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    import_run_id: UUID = Field(foreign_key="import_runs.id", index=True)
    partner_id: UUID | None = Field(
        default=None, foreign_key="partners.id", index=True
    )
    valuta_date: date = Field()
    booking_date: date = Field()
    amount: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    currency: str = Field(default="EUR", max_length=3)
    text: str | None = Field(default=None, max_length=1000)
    partner_name_raw: str | None = Field(default=None, max_length=500)
    partner_iban_raw: str | None = Field(default=None, max_length=34)
    unmapped_data: dict | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    import_run: ImportRun = Relationship(back_populates="lines")
```

---

## Schemas (Pydantic)

```python
# backend/app/imports/schemas.py

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from app.imports.models import ImportStatus


class ImportRunListItem(BaseModel):
    id: UUID
    filename: str
    row_count: int
    skipped_count: int
    error_count: int
    status: ImportStatus
    created_at: datetime
    completed_at: datetime | None


class ImportRunDetailResponse(ImportRunListItem):
    account_id: UUID
    user_id: UUID
    error_details: list | None


class PaginatedImportRunsResponse(BaseModel):
    items: list[ImportRunListItem]
    total: int
    page: int
    size: int
    pages: int
```

---

## Service-Schicht

### `ImportService`

```python
# backend/app/imports/service.py

import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import User
from app.imports.models import ImportRun, ImportStatus, JournalLine
from app.tenants.models import ColumnMapping


class ImportService:
    async def upload(
        self,
        session: AsyncSession,
        actor: User,
        account_id: UUID,
        mandant_id: UUID,
        files: list[UploadFile],
    ) -> list[ImportRun]:
        # Mapping laden
        mappings = await self._load_mappings(session, account_id)
        if not mappings:
            raise HTTPException(422, "No column mapping configured for this account")

        results = []
        for file in files:
            if not self._is_csv(file):
                raise HTTPException(422, f"File '{file.filename}' is not a CSV")
            run = await self._process_file(session, actor, account_id, mandant_id, file, mappings)
            results.append(run)
        return results

    async def _process_file(
        self,
        session: AsyncSession,
        actor: User,
        account_id: UUID,
        mandant_id: UUID,
        file: UploadFile,
        mappings: list[ColumnMapping],
    ) -> ImportRun:
        run = ImportRun(
            account_id=account_id,
            mandant_id=mandant_id,
            user_id=actor.id,
            filename=file.filename or "upload.csv",
            status=ImportStatus.pending,
        )
        session.add(run)
        await session.flush()   # run.id verfügbar

        run.status = ImportStatus.processing

        content = await file.read()
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))

        lines_to_insert: list[JournalLine] = []
        errors: list[dict] = []

        for row_num, row in enumerate(reader, start=1):
            mapped, unmapped = self._apply_mapping(row, mappings)
            field_errors = self._validate_required(mapped, row_num)
            if field_errors:
                errors.extend(field_errors)
                continue

            try:
                line = JournalLine(
                    account_id=account_id,
                    import_run_id=run.id,
                    valuta_date=date.fromisoformat(mapped["valuta_date"]),
                    booking_date=date.fromisoformat(mapped["booking_date"]),
                    amount=Decimal(mapped["amount"].replace(",", ".")),
                    currency=mapped.get("currency", "EUR")[:3],
                    text=mapped.get("text"),
                    partner_name_raw=mapped.get("partner_name"),
                    partner_iban_raw=mapped.get("partner_iban"),
                    unmapped_data=unmapped if unmapped else None,
                )
                lines_to_insert.append(line)
            except (ValueError, InvalidOperation) as e:
                errors.append({"row": row_num, "error": str(e)})

        inserted, skipped = await self._bulk_insert(session, lines_to_insert)

        run.row_count = inserted
        run.skipped_count = skipped
        run.error_count = len(errors)
        run.status = ImportStatus.completed if not errors else ImportStatus.completed
        # Nur failed wenn gar nichts importiert werden konnte und Fehler vorhanden
        if errors and inserted == 0 and skipped == 0:
            run.status = ImportStatus.failed
            run.error_details = errors
        run.completed_at = datetime.utcnow()
        session.add(run)

        return run

    def _apply_mapping(
        self,
        row: dict[str, str],
        mappings: list[ColumnMapping],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Gibt (mapped_fields, unmapped_fields) zurück."""
        mapped: dict[str, list[tuple[int, str]]] = {}
        mapped_sources: set[str] = set()

        for m in sorted(mappings, key=lambda x: x.sort_order):
            val = row.get(m.source_column, "")
            if m.target_column not in mapped:
                mapped[m.target_column] = []
            mapped[m.target_column].append((m.sort_order, val))
            mapped_sources.add(m.source_column)

        result: dict[str, str] = {
            target: "\n".join(v for _, v in sorted(vals))
            for target, vals in mapped.items()
        }
        unmapped = {k: v for k, v in row.items() if k not in mapped_sources}
        return result, unmapped

    def _validate_required(
        self, mapped: dict[str, str], row_num: int
    ) -> list[dict]:
        errors = []
        for field in ("valuta_date", "booking_date", "amount"):
            if not mapped.get(field):
                errors.append({"row": row_num, "error": f"required field '{field}' missing"})
        return errors

    async def _bulk_insert(
        self, session: AsyncSession, lines: list[JournalLine]
    ) -> tuple[int, int]:
        """
        Batch-Insert mit ON CONFLICT DO NOTHING.
        Gibt (inserted, skipped) zurück.
        """
        if not lines:
            return 0, 0
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.imports.models import JournalLine as JLModel

        stmt = pg_insert(JLModel).values(
            [
                {
                    "id": str(ln.id),
                    "account_id": str(ln.account_id),
                    "import_run_id": str(ln.import_run_id),
                    "valuta_date": ln.valuta_date,
                    "booking_date": ln.booking_date,
                    "amount": ln.amount,
                    "currency": ln.currency,
                    "text": ln.text,
                    "partner_name_raw": ln.partner_name_raw,
                    "partner_iban_raw": ln.partner_iban_raw,
                    "unmapped_data": ln.unmapped_data,
                    "created_at": ln.created_at,
                }
                for ln in lines
            ]
        ).on_conflict_do_nothing(index_elements=[
            "account_id", "valuta_date", "booking_date", "amount",
            "partner_iban_raw", "partner_name_raw",
        ])
        result = await session.execute(stmt)
        inserted = result.rowcount
        skipped = len(lines) - inserted
        return inserted, skipped

    def _is_csv(self, file: UploadFile) -> bool:
        return (
            (file.content_type or "").lower() in ("text/csv", "application/csv")
            or (file.filename or "").lower().endswith(".csv")
        )

    async def _load_mappings(
        self, session: AsyncSession, account_id: UUID
    ) -> list[ColumnMapping]:
        stmt = select(ColumnMapping).where(ColumnMapping.account_id == account_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_run(
        self, session: AsyncSession, run_id: UUID, account_id: UUID
    ) -> ImportRun:
        stmt = select(ImportRun).where(
            ImportRun.id == run_id, ImportRun.account_id == account_id
        )
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(404, "Import run not found")
        return run

    async def list_runs(
        self,
        session: AsyncSession,
        account_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[ImportRun], int]:
        from sqlalchemy import func
        offset = (page - 1) * size
        stmt = (
            select(ImportRun)
            .where(ImportRun.account_id == account_id)
            .order_by(ImportRun.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        count_stmt = select(func.count()).select_from(ImportRun).where(
            ImportRun.account_id == account_id
        )
        items = (await session.execute(stmt)).scalars().all()
        total = (await session.execute(count_stmt)).scalar_one()
        return list(items), total
```

---

## Router

```python
# backend/app/imports/router.py

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_session
from app.auth.dependencies import require_role
from app.auth.models import User
from app.imports.service import ImportService
from app.imports.schemas import ImportRunDetailResponse, ImportRunListItem, PaginatedImportRunsResponse

router = APIRouter(
    prefix="/mandants/{mandant_id}/accounts/{account_id}/imports",
    tags=["imports"],
)


@router.post("", response_model=list[ImportRunDetailResponse], status_code=201)
async def upload_csv(
    mandant_id: UUID,
    account_id: UUID,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("accountant")),
) -> list[ImportRunDetailResponse]:
    svc = ImportService()
    runs = await svc.upload(session, current_user, account_id, mandant_id, files)
    await session.commit()
    return [ImportRunDetailResponse.model_validate(r) for r in runs]


@router.get("", response_model=PaginatedImportRunsResponse)
async def list_import_runs(
    mandant_id: UUID,
    account_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("viewer")),
) -> PaginatedImportRunsResponse:
    svc = ImportService()
    items, total = await svc.list_runs(session, account_id, page, size)
    pages = (total + size - 1) // size
    return PaginatedImportRunsResponse(
        items=items, total=total, page=page, size=size, pages=pages
    )


@router.get("/{run_id}", response_model=ImportRunDetailResponse)
async def get_import_run(
    mandant_id: UUID,
    account_id: UUID,
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("viewer")),
) -> ImportRunDetailResponse:
    svc = ImportService()
    run = await svc.get_run(session, run_id, account_id)
    return ImportRunDetailResponse.model_validate(run)
```

---

## Modulstruktur

```
backend/app/
├── imports/
│   ├── __init__.py
│   ├── models.py        # ImportRun, JournalLine, ImportStatus
│   ├── schemas.py       # ImportRunListItem, ImportRunDetailResponse, Paginated...
│   ├── service.py       # ImportService (upload, get_run, list_runs)
│   └── router.py        # imports_router (nested unter mandants/accounts)
```

---

## Fehlerbehandlung

| Szenario | HTTP | Detail |
|----------|------|--------|
| Konto ohne ColumnMapping | 422 | `"No column mapping configured for this account"` |
| Datei kein CSV | 422 | `"File '{name}' is not a CSV"` |
| ImportRun nicht gefunden | 404 | `"Import run not found"` |
| Alle Zeilen Dubletten | 200 | `row_count=0, skipped_count=N, status=completed` |
| Pflichtfeld fehlt in gemappten Daten | — | `error_count` erhöhen, RowError in `error_details` |
| Viewer versucht Upload | 403 | `"Insufficient permissions"` |

---

## Migrations-Datei

`backend/alembic/versions/006_add_import_pipeline.py`

Erstellt: `import_status` ENUM, `import_runs`, `journal_lines` mit Dubletten-Index.

---

## Sicherheit

- Mandant-Scoping: `account_id` wird gegen `mandant_id` im Pfad geprüft (guard in Service via Account-Lookup aus Bolt 003)
- Dateiinhalt-Validierung: `content_type` und Dateiname werden geprüft; kein arbitrary file execution
- CSV-Parsing via `csv.DictReader` — keine Shell-Ausführung, kein Path-Traversal
- Pydantic/SQLModel validiert alle Felder vor dem Speichern
- `ON CONFLICT DO NOTHING` verhindert Dubletten ohne Race-Condition-Fehler

---

## Offene Entscheidungen (ADR-Kandidaten)

| Frage | Tendenz |
|-------|---------|
| Synchrone vs. asynchrone Verarbeitung | Synchron für MVP; Celery-Task bei Performance-Bedarf |
| CSV-Encoding | UTF-8 als Default; BOM-stripping via `utf-8-sig` |
| Max. Dateigröße | 10 MB pro Datei (FastAPI default); konfigurierbar |
