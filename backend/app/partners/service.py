import math
import re
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.partners.models import (
    AuditLog,
    MatchField,
    Partner,
    PartnerAccount,
    PartnerIban,
    PartnerName,
    PartnerPattern,
    PartnerPatternType,
)
from app.partners.schemas import (
    AddPatternRequest,
    AuditLogEntryResponse,
    MergeResponse,
    PaginatedAuditLogResponse,
    PartnerAccountResponse,
    PartnerDetailResponse,
    PartnerIbanResponse,
    PartnerListItem,
    PartnerNameResponse,
    PartnerNeighbor,
    PartnerNeighborsResponse,
    PartnerPatternResponse,
    PaginatedPartnersResponse,
)

log = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_iban(iban: str) -> str:
    return iban.replace(" ", "").upper()


class PartnerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_partners(
        self, mandant_id: UUID, page: int = 1, size: int = 20, include_inactive: bool = False, search: str = ""
    ) -> PaginatedPartnersResponse:
        size = min(size, 100)
        offset = (page - 1) * size

        base_filter = [Partner.mandant_id == mandant_id]  # type: ignore[list-item]
        if not include_inactive:
            base_filter.append(Partner.is_active == True)  # noqa: E712
        if search:
            term = f"%{search.lower()}%"
            base_filter.append(
                (text("lower(coalesce(display_name, name)) LIKE :term").bindparams(term=term))  # type: ignore[arg-type]
            )

        count_result = await self._session.exec(
            select(Partner.id).where(*base_filter)  # type: ignore[arg-type]
        )
        total = len(count_result.all())

        result = await self._session.exec(
            select(Partner)
            .where(*base_filter)
            .order_by(text("lower(name)"))
            .offset(offset)
            .limit(size)
        )
        partners = result.all()

        items = []
        for p in partners:
            iban_count = len((
                await self._session.exec(
                    select(PartnerIban.id).where(PartnerIban.partner_id == p.id)  # type: ignore[arg-type]
                )
            ).all())
            name_count = len((
                await self._session.exec(
                    select(PartnerName.id).where(PartnerName.partner_id == p.id)  # type: ignore[arg-type]
                )
            ).all())
            pattern_count = len((
                await self._session.exec(
                    select(PartnerPattern.id).where(
                        PartnerPattern.partner_id == p.id
                    )  # type: ignore[arg-type]
                )
            ).all())
            from app.imports.models import JournalLine
            journal_line_count = len((
                await self._session.exec(
                    select(JournalLine.id).where(JournalLine.partner_id == p.id)  # type: ignore[arg-type]
                )
            ).all())
            items.append(
                PartnerListItem(
                    id=p.id,
                    name=p.name,
                    display_name=p.display_name,
                    is_active=p.is_active,
                    iban_count=iban_count,
                    name_count=name_count,
                    pattern_count=pattern_count,
                    journal_line_count=journal_line_count,
                    created_at=p.created_at,
                )
            )

        return PaginatedPartnersResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=math.ceil(total / size) if total > 0 else 1,
        )

    async def get_partner(self, partner_id: UUID, mandant_id: UUID) -> Partner:
        partner = await self._session.get(Partner, partner_id)
        if partner is None or partner.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
        return partner

    async def get_neighbors(self, partner_id: UUID, mandant_id: UUID) -> PartnerNeighborsResponse:
        """Return the alphabetically previous and next active partner (by name)."""
        current = await self.get_partner(partner_id, mandant_id)
        current_name = current.name

        prev_result = await self._session.exec(
            select(Partner)
            .where(
                Partner.mandant_id == mandant_id,  # type: ignore[arg-type]
                Partner.name < current_name,
            )
            .order_by(text("name DESC"))
            .limit(1)
        )
        prev_partner = prev_result.first()

        next_result = await self._session.exec(
            select(Partner)
            .where(
                Partner.mandant_id == mandant_id,  # type: ignore[arg-type]
                Partner.name > current_name,
            )
            .order_by(Partner.name)
            .limit(1)
        )
        next_partner = next_result.first()

        return PartnerNeighborsResponse(
            prev=PartnerNeighbor(id=prev_partner.id, name=prev_partner.name) if prev_partner else None,
            next=PartnerNeighbor(id=next_partner.id, name=next_partner.name) if next_partner else None,
        )

    async def get_partner_detail(self, partner_id: UUID, mandant_id: UUID) -> PartnerDetailResponse:
        partner = await self.get_partner(partner_id, mandant_id)

        ibans_result = await self._session.exec(
            select(PartnerIban).where(PartnerIban.partner_id == partner_id)
        )
        accounts_result = await self._session.exec(
            select(PartnerAccount).where(PartnerAccount.partner_id == partner_id)
        )
        names_result = await self._session.exec(
            select(PartnerName).where(PartnerName.partner_id == partner_id)
        )
        patterns_result = await self._session.exec(
            select(PartnerPattern).where(PartnerPattern.partner_id == partner_id)
        )

        return PartnerDetailResponse(
            id=partner.id,
            mandant_id=partner.mandant_id,
            name=partner.name,
            display_name=partner.display_name,
            is_active=partner.is_active,
            ibans=[PartnerIbanResponse.model_validate(i) for i in ibans_result.all()],
            accounts=[PartnerAccountResponse.model_validate(a) for a in accounts_result.all()],
            names=[PartnerNameResponse.model_validate(n) for n in names_result.all()],
            patterns=[
                PartnerPatternResponse(
                    id=pp.id,
                    pattern=pp.pattern,
                    pattern_type=PartnerPatternType(pp.pattern_type),
                    match_field=MatchField(pp.match_field),
                    created_at=pp.created_at,
                )
                for pp in patterns_result.all()
            ],
            created_at=partner.created_at,
            updated_at=partner.updated_at,
        )

    async def update_display_name(
        self, partner_id: UUID, mandant_id: UUID, display_name: str | None
    ) -> PartnerDetailResponse:
        partner = await self.get_partner(partner_id, mandant_id)
        # Normalize empty string to None
        partner.display_name = display_name.strip() or None if display_name else None
        partner.updated_at = _utcnow()
        self._session.add(partner)
        await self._session.commit()
        await self._session.refresh(partner)
        return await self.get_partner_detail(partner_id, mandant_id)

    async def create_partner(
        self, mandant_id: UUID, name: str = "", iban: str | None = None
    ) -> Partner:
        # Uniqueness: name within mandant
        existing = await self._session.exec(
            select(Partner).where(Partner.mandant_id == mandant_id, Partner.name == name)
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Partner with this name already exists",
            )

        now = _utcnow()
        partner = Partner(mandant_id=mandant_id, name=name, created_at=now, updated_at=now)
        self._session.add(partner)
        await self._session.flush()  # get ID before creating IBAN

        from app.services.service import ensure_base_service

        await ensure_base_service(self._session, partner.id)

        if iban is not None:
            await self._add_iban_entity(partner.id, iban)

        await self._session.commit()
        await self._session.refresh(partner)
        log.info("partner_created", partner_id=str(partner.id), mandant_id=str(mandant_id))
        return partner

    async def add_iban(self, partner_id: UUID, mandant_id: UUID, iban: str) -> PartnerIban:
        await self.get_partner(partner_id, mandant_id)  # verify ownership
        return await self._add_iban_entity(partner_id, iban, commit=True)

    async def _add_iban_entity(
        self, partner_id: UUID, iban: str, commit: bool = False
    ) -> PartnerIban:
        normalized = _normalize_iban(iban)
        existing = await self._session.exec(
            select(PartnerIban).where(PartnerIban.iban == normalized)
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IBAN already assigned to another partner",
            )
        entity = PartnerIban(partner_id=partner_id, iban=normalized, created_at=_utcnow())
        self._session.add(entity)
        if commit:
            await self._session.commit()
            await self._session.refresh(entity)
        return entity

    async def remove_iban(self, iban_id: UUID, partner_id: UUID, mandant_id: UUID) -> None:
        await self.get_partner(partner_id, mandant_id)
        entity = await self._session.get(PartnerIban, iban_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IBAN not found")
        await self._session.delete(entity)
        await self._session.commit()

    async def add_account(
        self, partner_id: UUID, mandant_id: UUID, account_number: str, blz: str | None, bic: str | None = None
    ) -> PartnerAccount:
        await self.get_partner(partner_id, mandant_id)
        normalized_acct = account_number.strip().lstrip("0") or account_number.strip()
        normalized_blz = blz.strip() if blz else None
        normalized_bic = bic.strip().upper() if bic else None
        existing = await self._session.exec(
            select(PartnerAccount).where(
                PartnerAccount.account_number == normalized_acct,
                PartnerAccount.blz == normalized_blz,
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Kontonummer bereits einem Partner zugeordnet",
            )
        entity = PartnerAccount(
            partner_id=partner_id,
            blz=normalized_blz,
            account_number=normalized_acct,
            bic=normalized_bic,
            created_at=_utcnow(),
        )
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def remove_account(self, account_id: UUID, partner_id: UUID, mandant_id: UUID) -> None:
        await self.get_partner(partner_id, mandant_id)
        entity = await self._session.get(PartnerAccount, account_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kontonummer nicht gefunden")
        await self._session.delete(entity)
        await self._session.commit()

    async def add_name(self, partner_id: UUID, mandant_id: UUID, name: str) -> PartnerName:
        await self.get_partner(partner_id, mandant_id)
        existing = await self._session.exec(
            select(PartnerName).where(
                PartnerName.partner_id == partner_id, PartnerName.name == name
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Name variant already exists for this partner",
            )
        entity = PartnerName(partner_id=partner_id, name=name, created_at=_utcnow())
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def remove_name(self, name_id: UUID, partner_id: UUID, mandant_id: UUID) -> None:
        await self.get_partner(partner_id, mandant_id)
        entity = await self._session.get(PartnerName, name_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Name not found")
        await self._session.delete(entity)
        await self._session.commit()

    async def add_pattern(
        self, partner_id: UUID, mandant_id: UUID, data: AddPatternRequest
    ) -> PartnerPattern:
        await self.get_partner(partner_id, mandant_id)

        if data.pattern_type == PartnerPatternType.regex:
            try:
                re.compile(data.pattern)
            except re.error as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Invalid regex pattern: {exc}",
                ) from exc

        existing = await self._session.exec(
            select(PartnerPattern).where(
                PartnerPattern.partner_id == partner_id,
                PartnerPattern.pattern == data.pattern,
                PartnerPattern.match_field == data.match_field.value,
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pattern already exists for this partner and match field",
            )

        entity = PartnerPattern(
            partner_id=partner_id,
            pattern=data.pattern,
            pattern_type=data.pattern_type.value,
            match_field=data.match_field.value,
            created_at=_utcnow(),
        )
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def delete_pattern(
        self, pattern_id: UUID, partner_id: UUID, mandant_id: UUID
    ) -> None:
        await self.get_partner(partner_id, mandant_id)
        entity = await self._session.get(PartnerPattern, pattern_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found"
            )
        await self._session.delete(entity)
        await self._session.commit()

    async def preview_pattern(
        self, partner_id: UUID, mandant_id: UUID, data: AddPatternRequest
    ) -> list[PartnerNeighbor]:
        """Return other active partners whose stored identifiers match the given pattern."""

        def _matches(value: str) -> bool:
            if data.pattern_type == PartnerPatternType.string:
                return data.pattern.lower() in value.lower()
            try:
                return bool(re.search(data.pattern, value, re.IGNORECASE))
            except re.error:
                return False

        matched: dict[UUID, str] = {}

        if data.match_field == MatchField.partner_name:
            partners = (await self._session.exec(
                select(Partner).where(
                    Partner.mandant_id == mandant_id,  # type: ignore[arg-type]
                    Partner.is_active == True,  # noqa: E712
                    Partner.id != partner_id,
                )
            )).all()
            partner_map = {p.id: p for p in partners}
            if partner_map:
                name_entries = (await self._session.exec(
                    select(PartnerName)
                    .join(Partner, Partner.id == PartnerName.partner_id)
                    .where(
                        Partner.mandant_id == mandant_id,  # type: ignore[arg-type]
                        Partner.is_active == True,  # noqa: E712
                        PartnerName.partner_id != partner_id,
                    )
                )).all()
                for pn in name_entries:
                    if pn.partner_id not in matched and _matches(pn.name):
                        matched[pn.partner_id] = partner_map[pn.partner_id].name
                for p in partners:
                    if p.id not in matched and _matches(p.name):
                        matched[p.id] = p.name

        elif data.match_field == MatchField.partner_iban:
            partners = (await self._session.exec(
                select(Partner).where(
                    Partner.mandant_id == mandant_id,  # type: ignore[arg-type]
                    Partner.is_active == True,  # noqa: E712
                    Partner.id != partner_id,
                )
            )).all()
            partner_map = {p.id: p for p in partners}
            if partner_map:
                iban_entries = (await self._session.exec(
                    select(PartnerIban)
                    .join(Partner, Partner.id == PartnerIban.partner_id)
                    .where(
                        Partner.mandant_id == mandant_id,  # type: ignore[arg-type]
                        Partner.is_active == True,  # noqa: E712
                        PartnerIban.partner_id != partner_id,
                    )
                )).all()
                for pi in iban_entries:
                    if pi.partner_id not in matched and _matches(pi.iban):
                        matched[pi.partner_id] = partner_map[pi.partner_id].name

        return [PartnerNeighbor(id=pid, name=name) for pid, name in matched.items()]


class PartnerMergeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def merge(
        self,
        actor_id: UUID,
        mandant_id: UUID,
        source_id: UUID,
        target_id: UUID,
    ) -> MergeResponse:
        if source_id == target_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and target must be different",
            )

        source = await self._get_active_partner(source_id, mandant_id)
        target = await self._get_active_partner(target_id, mandant_id)

        # Transfer children (dedup-safe)
        await self._transfer_ibans(source_id, target_id)
        await self._transfer_names(source_id, target_id)
        await self._transfer_patterns(source_id, target_id)

        # Reassign journal lines (table may not exist before Bolt 006)
        lines_reassigned = await self._reassign_journal_lines(source_id, target_id, mandant_id)

        # Soft-delete source (ADR-009)
        source.is_active = False
        source.updated_at = _utcnow()
        self._session.add(source)

        # Audit log entry
        entry = AuditLog(
            mandant_id=mandant_id,
            event_type="partner.merged",
            actor_id=actor_id,
            payload={
                "source_partner_id": str(source_id),
                "target_partner_id": str(target_id),
                "lines_reassigned": lines_reassigned,
            },
        )
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(target)
        await self._session.refresh(entry)

        log.info(
            "partner_merged",
            source_id=str(source_id),
            target_id=str(target_id),
            lines_reassigned=lines_reassigned,
        )

        partner_svc = PartnerService(self._session)
        target_detail = await partner_svc.get_partner_detail(target_id, mandant_id)
        return MergeResponse(
            target=target_detail,
            lines_reassigned=lines_reassigned,
            audit_log_id=entry.id,
        )

    async def _get_active_partner(self, partner_id: UUID, mandant_id: UUID) -> Partner:
        result = await self._session.exec(
            select(Partner).where(
                Partner.id == partner_id,
                Partner.mandant_id == mandant_id,
                Partner.is_active == True,  # noqa: E712
            )
        )
        partner = result.first()
        if partner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Partner not found or inactive",
            )
        return partner

    async def _transfer_ibans(self, source_id: UUID, target_id: UUID) -> None:
        target_existing = (
            await self._session.exec(
                select(PartnerIban.iban).where(PartnerIban.partner_id == target_id)
            )
        ).all()
        target_set = set(target_existing)

        source_ibans = (
            await self._session.exec(
                select(PartnerIban).where(PartnerIban.partner_id == source_id)
            )
        ).all()

        for pi in source_ibans:
            if pi.iban in target_set:
                await self._session.delete(pi)
            else:
                pi.partner_id = target_id
                self._session.add(pi)

        await self._session.flush()

    async def _transfer_names(self, source_id: UUID, target_id: UUID) -> None:
        target_existing = (
            await self._session.exec(
                select(PartnerName.name).where(PartnerName.partner_id == target_id)
            )
        ).all()
        target_set = set(target_existing)

        source_names = (
            await self._session.exec(
                select(PartnerName).where(PartnerName.partner_id == source_id)
            )
        ).all()

        for pn in source_names:
            if pn.name in target_set:
                await self._session.delete(pn)
            else:
                pn.partner_id = target_id
                self._session.add(pn)

        await self._session.flush()

    async def _transfer_patterns(self, source_id: UUID, target_id: UUID) -> None:
        target_existing = (
            await self._session.exec(
                select(PartnerPattern).where(PartnerPattern.partner_id == target_id)
            )
        ).all()
        target_keys = {(pp.pattern, pp.match_field) for pp in target_existing}

        source_patterns = (
            await self._session.exec(
                select(PartnerPattern).where(PartnerPattern.partner_id == source_id)
            )
        ).all()

        for pp in source_patterns:
            if (pp.pattern, pp.match_field) in target_keys:
                await self._session.delete(pp)
            else:
                pp.partner_id = target_id
                self._session.add(pp)

        await self._session.flush()

    async def _reassign_journal_lines(
        self, source_id: UUID, target_id: UUID, mandant_id: UUID
    ) -> int:
        try:
            from app.imports.models import JournalLine
            from app.tenants.models import Account as _Account

            # Collect account IDs scoped to this mandant
            account_ids_result = await self._session.exec(
                select(_Account.id).where(_Account.mandant_id == mandant_id)
            )
            account_ids_set = set(account_ids_result.all())
            if not account_ids_set:
                return 0

            # Fetch all lines for source partner then filter by mandant accounts in Python
            all_lines = (
                await self._session.exec(
                    select(JournalLine).where(JournalLine.partner_id == source_id)
                )
            ).all()
            lines = [ln for ln in all_lines if ln.account_id in account_ids_set]

            for line in lines:
                line.partner_id = target_id
                self._session.add(line)

            await self._session.flush()
            return len(lines)
        except (SQLAlchemyError, ImportError):
            # journal_lines table not yet created (Bolt 006 not run)
            return 0


class AuditLogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_mandant(
        self,
        mandant_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedAuditLogResponse:
        size = min(size, 100)
        offset = (page - 1) * size

        # Zeige Einträge dieses Mandanten UND system-weite Einträge (mandant_id IS NULL)
        where_clause = (
            (AuditLog.mandant_id == mandant_id) | (AuditLog.mandant_id == None)  # noqa: E711
        )

        total = len((
            await self._session.exec(
                select(AuditLog.id).where(where_clause)  # type: ignore[arg-type]
            )
        ).all())

        items = (
            await self._session.exec(
                select(AuditLog)
                .where(where_clause)
                .order_by(text("created_at DESC"))
                .offset(offset)
                .limit(size)
            )
        ).all()

        return PaginatedAuditLogResponse(
            items=[AuditLogEntryResponse.model_validate(e) for e in items],
            total=total,
            page=page,
            size=size,
            pages=math.ceil(total / size) if total > 0 else 1,
        )
