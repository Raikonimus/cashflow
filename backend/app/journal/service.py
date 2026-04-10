import math
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.imports.models import JournalLine
from app.partners.models import AuditLog, Partner
from app.services.service import ServiceManagementService
from app.tenants.models import Account
from app.journal.schemas import (
    BulkAssignResponse,
    JournalLineResponse,
    PaginatedJournalResponse,
)

log = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JournalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── List lines ──────────────────────────────────────────────────────────

    async def list_lines(
        self,
        mandant_id: UUID,
        *,
        account_id: UUID | None = None,
        partner_id: UUID | None = None,
        year: int | None = None,
        month: int | None = None,
        has_partner: bool | None = None,
        search: str = "",
        sort_by: str = "valuta_date",
        sort_dir: str = "desc",
        page: int = 1,
        size: int = 50,
    ) -> PaginatedJournalResponse:
        size = min(size, 200)
        offset = (page - 1) * size

        # All account IDs belonging to this mandant (security boundary)
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        if account_id is not None:
            if account_id not in mandant_account_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account does not belong to this mandant",
                )
            account_ids_filter = {account_id}
        else:
            account_ids_filter = mandant_account_ids

        query = select(JournalLine).where(
            col(JournalLine.account_id).in_(account_ids_filter)
        )

        if partner_id is not None:
            query = query.where(JournalLine.partner_id == partner_id)

        if has_partner is True:
            query = query.where(text("journal_lines.partner_id IS NOT NULL"))
        elif has_partner is False:
            query = query.where(text("journal_lines.partner_id IS NULL"))

        if year is not None and month is not None:
            prefix = f"{year:04d}-{month:02d}-"
            query = query.where(text("journal_lines.valuta_date LIKE :valuta_prefix").bindparams(valuta_prefix=f"{prefix}%"))
        elif year is not None:
            query = query.where(text("journal_lines.valuta_date LIKE :valuta_year").bindparams(valuta_year=f"{year:04d}-%"))

        if search:
            # Always JOIN partners for search (avoid duplicate join if also sorting by partner_name)
            term = f"%{search.lower()}%"
            query = (
                query
                .outerjoin(Partner, Partner.id == JournalLine.partner_id)  # type: ignore[arg-type]
                .where(
                    text(
                        "lower(coalesce(journal_lines.text,'')) LIKE :term"
                        " OR lower(coalesce(journal_lines.partner_name_raw,'')) LIKE :term"
                        " OR lower(coalesce(partners.display_name, partners.name,'')) LIKE :term"
                    ).bindparams(term=term)
                )
            )

        # Sorting: partner_name requires JOIN; others are plain SQL columns
        SQL_SORT_COLS = {"valuta_date", "booking_date", "amount", "text"}
        if sort_by in SQL_SORT_COLS:
            order_expr = text(f"{sort_by} {'DESC' if sort_dir == 'desc' else 'ASC'}")
        elif sort_by == "partner_name":
            # JOIN partners so we can ORDER BY coalesce(display_name, name) globally
            # Only join if not already joined via search
            order_dir = "DESC" if sort_dir == "desc" else "ASC"
            if not search:  # search already added the join
                query = query.outerjoin(Partner, Partner.id == JournalLine.partner_id)  # type: ignore[arg-type]
            order_expr = text(
                f"lower(coalesce(partners.display_name, partners.name, journal_lines.partner_name_raw, '')) {order_dir}"
            )
        else:
            order_expr = text("valuta_date DESC")  # fallback

        count_res = await self._session.exec(query)
        total = len(count_res.all())

        data_res = await self._session.exec(
            query.order_by(order_expr).offset(offset).limit(size)
        )
        lines = data_res.all()

        # Batch-load partner names (prefer display_name)
        partner_ids = {ln.partner_id for ln in lines if ln.partner_id}
        partner_names: dict = {}
        if partner_ids:
            p_res = await self._session.exec(
                select(Partner)
            )
            partner_names = {
                partner.id: partner.display_name or partner.name
                for partner in p_res.all()
                if partner.id in partner_ids
            }

        items = [
            JournalLineResponse(
                **{k: v for k, v in ln.model_dump().items()},
                partner_name=partner_names.get(ln.partner_id) if ln.partner_id else None,
            )
            for ln in lines
        ]

        return PaginatedJournalResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=math.ceil(total / size) if total > 0 else 1,
        )

    # ─── Bulk-assign ─────────────────────────────────────────────────────────

    async def bulk_assign(
        self,
        mandant_id: UUID,
        actor_id: UUID,
        line_ids: list[UUID],
        partner_id: UUID,
    ) -> BulkAssignResponse:
        if not line_ids:
            return BulkAssignResponse(assigned=0, skipped=0)

        # Security: resolve all mandant accounts once
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        lines_res = await self._session.exec(
            select(JournalLine).where(col(JournalLine.id).in_(line_ids))
        )
        lines = lines_res.all()

        # Reject request if any requested line belongs to a different mandant
        foreign = [ln for ln in lines if ln.account_id not in mandant_account_ids]
        if foreign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One or more journal lines do not belong to this mandant",
            )

        assigned = 0
        skipped = 0
        for ln in lines:
            if ln.partner_id == partner_id:
                skipped += 1
                continue
            ln.partner_id = partner_id
            self._session.add(ln)
            assigned += 1

        # Single audit log entry for the whole operation
        entry = AuditLog(
            mandant_id=mandant_id,
            event_type="journal.bulk_assign",
            actor_id=actor_id,
            payload={
                "partner_id": str(partner_id),
                "line_ids": [str(lid) for lid in line_ids],
                "assigned": assigned,
                "skipped": skipped,
            },
        )
        self._session.add(entry)
        await self._session.commit()

        log.info(
            "journal_bulk_assigned",
            mandant_id=str(mandant_id),
            partner_id=str(partner_id),
            assigned=assigned,
        )
        return BulkAssignResponse(assigned=assigned, skipped=skipped)

    async def assign_service(
        self,
        mandant_id: UUID,
        actor_id: UUID,
        line_id: UUID,
        service_id: UUID,
    ) -> JournalLineResponse:
        line = await self._session.get(JournalLine, line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        account = await self._session.get(Account, line.account_id)
        if account is None or account.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Journal line does not belong to this mandant")

        service_svc = ServiceManagementService(self._session)
        await service_svc.manually_assign_journal_line(mandant_id, line, service_id)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="journal.service_assigned",
                actor_id=actor_id,
                payload={
                    "journal_line_id": str(line.id),
                    "service_id": str(service_id),
                },
            )
        )
        await self._session.commit()
        await self._session.refresh(line)

        partner_name = None
        if line.partner_id is not None:
            partner = await self._session.get(Partner, line.partner_id)
            if partner is not None:
                partner_name = partner.display_name or partner.name

        return JournalLineResponse(
            **{key: value for key, value in line.model_dump().items()},
            partner_name=partner_name,
        )
