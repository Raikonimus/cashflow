---
stage: technical-design
bolt: 005-partner-merge
created: 2026-04-06T00:00:00Z
---

# Technical Design: Partner Merge (Bolt 005)

## API-Endpunkte

| Method | Path | Role | Beschreibung |
|--------|------|------|-------------|
| POST | `/api/v1/mandants/{mandant_id}/partners/{target_id}/merge` | accountant+ | Source-Partner in Target mergen |
| GET | `/api/v1/mandants/{mandant_id}/audit-log` | viewer+ | Paginierter Audit-Log für Mandant |

---

## Datenbankschema

```sql
-- Migration 005: partner_merge + audit_log

-- Audit-Log Tabelle (mandantenübergreifend nutzbar, mandant-scoped)
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mandant_id  UUID NOT NULL REFERENCES mandants(id) ON DELETE CASCADE,
    event_type  VARCHAR(100) NOT NULL,
    actor_id    UUID NOT NULL REFERENCES users(id),
    payload     JSONB NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_mandant_id ON audit_log(mandant_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);

-- Kein neues Schema für partners/journal_lines notwendig:
-- Die Merge-Operation schreibt nur is_active=false (partners)
-- und UPDATE partner_id (journal_lines – Tabelle kommt in Bolt 006)
```

**Hinweis**: `journal_lines` wird in Bolt 006 (Migration 006) angelegt. Die FK-Referenz in der Merge-Operation erfolgt via SQL-Update, nicht über eine neue Constraint-Änderung.

---

## SQLModel-Modelle

```python
# backend/app/partners/models.py  (Ergänzung zu Bolt 004)

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    event_type: str = Field(max_length=100)
    actor_id: UUID = Field(foreign_key="users.id")
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## Schemas (Pydantic)

```python
# backend/app/partners/schemas.py  (Ergänzung)

class MergeRequest(BaseModel):
    source_id: UUID

class MergeResponse(BaseModel):
    target: PartnerDetailResponse
    lines_reassigned: int
    audit_log_id: UUID

class AuditLogEntryResponse(BaseModel):
    id: UUID
    event_type: str
    actor_id: UUID
    payload: dict
    created_at: datetime

class PaginatedAuditLogResponse(BaseModel):
    items: list[AuditLogEntryResponse]
    total: int
    page: int
    size: int
    pages: int
```

---

## Service-Schicht

### `PartnerMergeService`

```python
# backend/app/partners/service.py  (Ergänzung)

class PartnerMergeService:
    async def merge(
        self,
        session: AsyncSession,
        actor: User,
        mandant_id: UUID,
        source_id: UUID,
        target_id: UUID,
    ) -> MergeResult:
        # 1. Validierungen
        if source_id == target_id:
            raise HTTPException(400, "Source and target must be different")

        source = await self._get_active_partner(session, source_id, mandant_id)
        target = await self._get_active_partner(session, target_id, mandant_id)

        # 2. Transaktion: IBANs, Namen, Patterns übertragen (Duplikate lautlos ignorieren)
        async with session.begin_nested():
            await self._transfer_children(session, source, target)
            lines_reassigned = await self._reassign_journal_lines(
                session, source_id, target_id, mandant_id
            )
            source.is_active = False
            source.updated_at = datetime.utcnow()
            session.add(source)

            audit_entry = AuditLog(
                mandant_id=mandant_id,
                event_type="partner.merged",
                actor_id=actor.id,
                payload={
                    "source_partner_id": str(source_id),
                    "target_partner_id": str(target_id),
                    "lines_reassigned": lines_reassigned,
                },
            )
            session.add(audit_entry)

        return MergeResult(
            target=target,
            lines_reassigned=lines_reassigned,
            audit_log_id=audit_entry.id,
        )

    async def _transfer_children(
        self, session: AsyncSession, source: Partner, target: Partner
    ) -> None:
        # IBANs: UPDATE partner_ibans SET partner_id=target WHERE partner_id=source
        #        ON CONFLICT (iban) DO NOTHING
        await session.execute(
            text("""
                UPDATE partner_ibans
                SET partner_id = :target_id
                WHERE partner_id = :source_id
                  AND iban NOT IN (
                      SELECT iban FROM partner_ibans WHERE partner_id = :target_id
                  )
            """),
            {"target_id": target.id, "source_id": source.id},
        )
        # Restliche IBANs von source die Duplikat sind → löschen
        await session.execute(
            text("DELETE FROM partner_ibans WHERE partner_id = :source_id"),
            {"source_id": source.id},
        )

        # Namen analog
        await session.execute(
            text("""
                UPDATE partner_names
                SET partner_id = :target_id
                WHERE partner_id = :source_id
                  AND name NOT IN (
                      SELECT name FROM partner_names WHERE partner_id = :target_id
                  )
            """),
            {"target_id": target.id, "source_id": source.id},
        )
        await session.execute(
            text("DELETE FROM partner_names WHERE partner_id = :source_id"),
            {"source_id": source.id},
        )

        # Patterns analog (unique auf partner_id + pattern + match_field)
        await session.execute(
            text("""
                UPDATE partner_patterns
                SET partner_id = :target_id
                WHERE partner_id = :source_id
                  AND (pattern, match_field) NOT IN (
                      SELECT pattern, match_field
                      FROM partner_patterns WHERE partner_id = :target_id
                  )
            """),
            {"target_id": target.id, "source_id": source.id},
        )
        await session.execute(
            text("DELETE FROM partner_patterns WHERE partner_id = :source_id"),
            {"source_id": source.id},
        )

    async def _reassign_journal_lines(
        self,
        session: AsyncSession,
        source_id: UUID,
        target_id: UUID,
        mandant_id: UUID,
    ) -> int:
        # journal_lines existiert erst nach Bolt 006 — guard mit try/except
        result = await session.execute(
            text("""
                UPDATE journal_lines jl
                SET partner_id = :target_id
                FROM accounts a
                WHERE jl.partner_id = :source_id
                  AND jl.account_id = a.id
                  AND a.mandant_id = :mandant_id
            """),
            {
                "target_id": str(target_id),
                "source_id": str(source_id),
                "mandant_id": str(mandant_id),
            },
        )
        return result.rowcount

    async def _get_active_partner(
        self, session: AsyncSession, partner_id: UUID, mandant_id: UUID
    ) -> Partner:
        stmt = select(Partner).where(
            Partner.id == partner_id,
            Partner.mandant_id == mandant_id,
            Partner.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        partner = result.scalar_one_or_none()
        if partner is None:
            raise HTTPException(404, "Partner not found or inactive")
        return partner


class AuditLogService:
    async def list_by_mandant(
        self,
        session: AsyncSession,
        mandant_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[AuditLog], int]:
        offset = (page - 1) * size
        stmt = (
            select(AuditLog)
            .where(AuditLog.mandant_id == mandant_id)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        count_stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.mandant_id == mandant_id
        )
        items = (await session.execute(stmt)).scalars().all()
        total = (await session.execute(count_stmt)).scalar_one()
        return list(items), total
```

---

## Router

```python
# backend/app/partners/router.py  (Ergänzung)

@router.post(
    "/{target_id}/merge",
    response_model=MergeResponse,
    status_code=200,
)
async def merge_partners(
    mandant_id: UUID,
    target_id: UUID,
    body: MergeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("accountant")),
) -> MergeResponse:
    svc = PartnerMergeService()
    result = await svc.merge(session, current_user, mandant_id, body.source_id, target_id)
    ...


# Separater Audit-Log Router (unter mandants)
@audit_router.get(
    "",
    response_model=PaginatedAuditLogResponse,
)
async def list_audit_log(
    mandant_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("viewer")),
) -> PaginatedAuditLogResponse:
    svc = AuditLogService()
    items, total = await svc.list_by_mandant(session, mandant_id, page, size)
    ...
```

---

## Modulstruktur

```
backend/app/
├── partners/
│   ├── models.py        # + AuditLog (Ergänzung)
│   ├── schemas.py       # + MergeRequest, MergeResponse, AuditLogEntryResponse
│   ├── service.py       # + PartnerMergeService, AuditLogService
│   └── router.py        # + merge endpoint, audit_log sub-router
```

---

## Fehlerbehandlung

| Szenario | HTTP | Detail |
|----------|------|--------|
| source_id == target_id | 400 | `"Source and target must be different"` |
| Partner nicht gefunden (falsche mandant_id oder inaktiv) | 404 | `"Partner not found or inactive"` |
| Viewer versucht zu mergen | 403 | `"Insufficient permissions"` |
| journal_lines-Tabelle noch nicht vorhanden (Bolt 005 vor 006) | — | `_reassign_journal_lines` gibt 0 zurück; kein Fehler |

---

## Migrations-Datei

`backend/alembic/versions/005_add_audit_log.py`

Erstellt: `audit_log` Tabelle mit allen Indizes. Keine Änderungen an bestehenden Tabellen.

---

## Sicherheit

- Mandant-Scoping: `mandant_id` im Pfad wird gegen die Session-User-Mandanten-Zugehörigkeit geprüft (bestehender JWT-Middleware-Mechanismus aus Bolt 001)
- Merge-Endpoint benötigt mindestens `accountant`-Rolle
- Audit-Log-Lesen ab `viewer`-Rolle
- `payload` JSONB enthält keine sensiblen Daten (nur UUIDs + Zähler)
