import math
from enum import Enum
from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.partners.models import (
    AuditLog,
    Partner,
    PartnerAccount,
    PartnerIban,
    PartnerName,
)
from app.partners.delete_utils import delete_partner_clean
from app.partners.conflict_utils import PartnerAssignmentCriteria, detect_conflicting_criteria, load_partner_assignment_criteria
from app.partners.schemas import (
    AuditLogEntryResponse,
    MergeResponse,
    PaginatedAuditLogResponse,
    PartnerAccountResponse,
    PartnerDetailResponse,
    PartnerIbanResponse,
    PartnerNeighbor,
    PartnerListItem,
    PartnerNameResponse,
    PartnerNeighborsResponse,
    PaginatedPartnersResponse,
)
from app.services.models import Service, ServiceType
from app.services.service import ServiceManagementService

log = structlog.get_logger()

SERVICE_TYPE_ORDER: dict[str, int] = {
    ServiceType.customer.value: 0,
    ServiceType.supplier.value: 1,
    ServiceType.employee.value: 2,
    ServiceType.shareholder.value: 3,
    ServiceType.authority.value: 4,
    ServiceType.internal_transfer.value: 5,
    ServiceType.unknown.value: 6,
}


class PartnerSortField(str, Enum):
    name = "name"
    iban_count = "iban_count"
    name_count = "name_count"
    journal_line_count = "journal_line_count"
    status = "status"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_iban(iban: str) -> str:
    return iban.replace(" ", "").upper()


class PartnerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_partners(
        self,
        mandant_id: UUID,
        page: int = 1,
        size: int = 20,
        include_inactive: bool = False,
        search: str = "",
        service_type: ServiceType | None = None,
        sort_by: PartnerSortField = PartnerSortField.name,
        sort_dir: SortDirection = SortDirection.asc,
    ) -> PaginatedPartnersResponse:
        size = min(size, 100)

        base_filter = [Partner.mandant_id == mandant_id]  # type: ignore[list-item]
        if not include_inactive:
            base_filter.append(Partner.is_active == True)  # noqa: E712
        if search:
            term = f"%{search.lower()}%"
            # IBAN-Suche: Leerzeichen entfernen und Großbuchstaben für normalisierte IBANs
            iban_term = f"%{search.replace(' ', '').upper()}%"
            iban_subq = select(PartnerIban.partner_id).where(
                PartnerIban.iban.like(iban_term)  # type: ignore[union-attr]
            )
            account_subq = select(PartnerAccount.partner_id).where(
                PartnerAccount.account_number.ilike(term)  # type: ignore[union-attr]
            )
            base_filter.append(
                or_(
                    text("lower(coalesce(display_name, name)) LIKE :term").bindparams(term=term),
                    Partner.id.in_(iban_subq),  # type: ignore[arg-type]
                    Partner.id.in_(account_subq),  # type: ignore[arg-type]
                )  # type: ignore[arg-type]
            )
        result = await self._session.exec(select(Partner).where(*base_filter).order_by(text("lower(name)")))
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
            from app.imports.models import JournalLine
            journal_line_count = len((
                await self._session.exec(
                    select(JournalLine.id).where(JournalLine.partner_id == p.id)  # type: ignore[arg-type]
                )
            ).all())
            service_types = sorted(
                {
                    service_type
                    for service_type in (
                        await self._session.exec(
                            select(Service.service_type).where(Service.partner_id == p.id)  # type: ignore[arg-type]
                        )
                    ).all()
                    if service_type
                },
                key=lambda service_type: SERVICE_TYPE_ORDER.get(service_type, len(SERVICE_TYPE_ORDER)),
            )
            if service_type is not None and service_type.value not in service_types:
                continue
            items.append(
                PartnerListItem(
                    id=p.id,
                    name=p.name,
                    display_name=p.display_name,
                    is_active=p.is_active,
                    service_types=service_types,
                    iban_count=iban_count,
                    name_count=name_count,
                    journal_line_count=journal_line_count,
                    created_at=p.created_at,
                )
            )

        total = len(items)

        reverse = sort_dir == SortDirection.desc
        if sort_by == PartnerSortField.name:
            items.sort(key=lambda item: (item.display_name or item.name).lower(), reverse=reverse)
        elif sort_by == PartnerSortField.iban_count:
            items.sort(key=lambda item: (item.iban_count, (item.display_name or item.name).lower()), reverse=reverse)
        elif sort_by == PartnerSortField.name_count:
            items.sort(key=lambda item: (item.name_count, (item.display_name or item.name).lower()), reverse=reverse)
        elif sort_by == PartnerSortField.journal_line_count:
            items.sort(key=lambda item: (item.journal_line_count, (item.display_name or item.name).lower()), reverse=reverse)
        elif sort_by == PartnerSortField.status:
            items.sort(key=lambda item: (item.is_active, (item.display_name or item.name).lower()), reverse=reverse)

        offset = (page - 1) * size
        paged_items = items[offset:offset + size]

        return PaginatedPartnersResponse(
            items=paged_items,
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

        return PartnerDetailResponse(
            id=partner.id,
            mandant_id=partner.mandant_id,
            name=partner.name,
            display_name=partner.display_name,
            is_active=partner.is_active,
            ibans=[PartnerIbanResponse.model_validate(i) for i in ibans_result.all()],
            accounts=[PartnerAccountResponse.model_validate(a) for a in accounts_result.all()],
            names=[PartnerNameResponse.model_validate(n) for n in names_result.all()],
            created_at=partner.created_at,
            updated_at=partner.updated_at,
        )

    async def delete_partner(self, partner_id: UUID, mandant_id: UUID) -> None:
        partner = await self.get_partner(partner_id, mandant_id)

        await delete_partner_clean(
            self._session,
            partner,
            detach_journal_lines=not partner.is_active,
        )
        await self._session.commit()

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

    async def preview_iban(
        self,
        partner_id: UUID,
        mandant_id: UUID,
        iban: str,
    ) -> "AccountPreviewResponse":
        """Gibt alle Buchungszeilen zurück, die zu dieser IBAN passen,
        aber NICHT zum angegebenen Partner gehören."""
        from app.imports.models import JournalLine
        from app.partners.schemas import AccountPreviewLineItem, AccountPreviewResponse
        from decimal import Decimal

        await self.get_partner(partner_id, mandant_id)
        normalized_iban = _normalize_iban(iban)

        lines = (
            await self._session.exec(
                select(JournalLine)
                .where(
                    JournalLine.partner_iban_raw == normalized_iban,
                )
            )
        ).all()

        # Fallback: auch nach Teiltreffer suchen (raw-Vergleich)
        if not lines:
            lines = (
                await self._session.exec(
                    select(JournalLine)
                    .where(
                        JournalLine.partner_iban_raw.ilike(f"%{normalized_iban}%"),  # type: ignore[union-attr]
                    )
                )
            ).all()

        # Nur Zeilen desselben Mandanten
        from app.tenants.models import Account as _Account
        account_ids = set(
            (await self._session.exec(select(_Account.id).where(_Account.mandant_id == mandant_id))).all()
        )
        lines = [ln for ln in lines if ln.account_id in account_ids]

        partner_name_cache: dict[UUID | None, str | None] = {}
        service_name_cache: dict[UUID | None, str | None] = {None: None}
        partner_conflict_cache: dict[UUID, PartnerAssignmentCriteria] = {}
        matched: list[AccountPreviewLineItem] = []
        for line in lines:
            if line.partner_id not in partner_name_cache:
                if line.partner_id is None:
                    partner_name_cache[None] = None
                else:
                    p = await self._session.get(Partner, line.partner_id)
                    partner_name_cache[line.partner_id] = ((p.display_name or p.name) if p else None)
            if line.service_id not in service_name_cache:
                current_service = await self._session.get(Service, line.service_id)
                service_name_cache[line.service_id] = current_service.name if current_service else None
            conflict_reasons: list[str] = []
            if line.partner_id is not None and line.partner_id != partner_id:
                if line.partner_id not in partner_conflict_cache:
                    partner_conflict_cache[line.partner_id] = await load_partner_assignment_criteria(self._session, line.partner_id)
                conflict_reasons = detect_conflicting_criteria(partner_conflict_cache[line.partner_id], line)
            matched.append(AccountPreviewLineItem(
                journal_line_id=line.id,
                partner_name_raw=line.partner_name_raw,
                current_partner_name=partner_name_cache.get(line.partner_id),
                current_service_name=service_name_cache.get(line.service_id),
                has_conflicting_partner_criteria=bool(conflict_reasons),
                conflicting_partner_criteria=conflict_reasons,
                booking_date=line.booking_date,
                valuta_date=line.valuta_date,
                amount=Decimal(str(line.amount)),
                currency=line.currency,
                text=line.text,
                already_assigned=line.partner_id == partner_id,
            ))

        matched.sort(key=lambda x: x.booking_date, reverse=True)
        matched.sort(key=lambda x: not x.has_conflicting_partner_criteria)
        return AccountPreviewResponse(matched_lines=matched, total=len(matched))

    async def add_iban_with_reassign(
        self,
        partner_id: UUID,
        mandant_id: UUID,
        iban: str,
    ) -> PartnerIban:
        """Speichert IBAN und weist passende Buchungszeilen dem Partner zu.
        Es werden nur die tatsächlich gematchten Zeilen verschoben;
        Source-Partner werden nur gelöscht, falls danach keine Zeilen mehr vorhanden sind."""
        from app.imports.models import JournalLine

        await self.get_partner(partner_id, mandant_id)
        normalized_iban = _normalize_iban(iban)

        entity = await self._add_iban_entity(partner_id, normalized_iban, commit=False)

        # Buchungszeilen desselben Mandanten mit dieser IBAN suchen (nur fremde)
        from app.tenants.models import Account as _Account
        account_ids = set(
            (await self._session.exec(select(_Account.id).where(_Account.mandant_id == mandant_id))).all()
        )

        # NULL != UUID ergibt in SQL NULL (falsy) -> explizit IS NULL einschließen
        not_this_partner = or_(
            JournalLine.partner_id != partner_id,
            JournalLine.partner_id.is_(None),  # type: ignore[union-attr]
        )
        matching_lines = (
            await self._session.exec(
                select(JournalLine)
                .where(
                    JournalLine.partner_iban_raw == normalized_iban,
                    not_this_partner,
                )
            )
        ).all()
        if not matching_lines:
            matching_lines = (
                await self._session.exec(
                    select(JournalLine)
                    .where(
                        JournalLine.partner_iban_raw.ilike(f"%{normalized_iban}%"),  # type: ignore[union-attr]
                        not_this_partner,
                    )
                )
            ).all()

        matching_lines = [ln for ln in matching_lines if ln.account_id in account_ids]

        # Zeilen ohne Partner direkt zuordnen; Zeilen fremder Partner nur selektiv verschieben
        unassigned_lines = [ln for ln in matching_lines if ln.partner_id is None]
        matching_by_partner: dict[UUID, list[JournalLine]] = {}
        for ln in matching_lines:
            if ln.partner_id is not None:
                matching_by_partner.setdefault(ln.partner_id, []).append(ln)

        svc_svc = ServiceManagementService(self._session)
        needs_revalidation = False

        if unassigned_lines:
            await svc_svc.prepare_lines_for_partner_change(mandant_id, unassigned_lines, partner_id)
            needs_revalidation = True

        if matching_by_partner:
            for src_id, matched_lines in matching_by_partner.items():
                await svc_svc.prepare_lines_for_partner_change(mandant_id, list(matched_lines), partner_id)
                needs_revalidation = True

                # Source-Partner löschen wenn leer (wie Service-Matcher-Flow)
                remaining = (
                    await self._session.exec(
                        select(JournalLine.id).where(JournalLine.partner_id == src_id).limit(1)
                    )
                ).first()
                if remaining is None:
                    src_partner = await self._session.get(Partner, src_id)
                    if src_partner is not None and src_partner.mandant_id == mandant_id:
                        await delete_partner_clean(
                            self._session,
                            src_partner,
                            detach_journal_lines=False,
                        )

        if needs_revalidation:
            await svc_svc.revalidate_partner_lines(partner_id)
        else:
            await self._session.commit()

        await self._session.refresh(entity)
        return entity

    async def remove_iban(self, iban_id: UUID, partner_id: UUID, mandant_id: UUID) -> None:
        await self.get_partner(partner_id, mandant_id)  # verify ownership
        entity = await self._session.get(PartnerIban, iban_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IBAN not found")
        await self._session.delete(entity)
        await self._session.commit()

    async def add_account(
        self,
        partner_id: UUID,
        mandant_id: UUID,
        account_number: str,
        blz: str | None = None,
        bic: str | None = None,
    ) -> PartnerAccount:
        await self.get_partner(partner_id, mandant_id)  # verify ownership
        normalized_acct, normalized_blz, normalized_bic = self._normalize_account_fields(account_number, blz, bic)
        await self._ensure_account_available(normalized_acct, normalized_blz)
        entity = PartnerAccount(
            partner_id=partner_id,
            account_number=normalized_acct,
            blz=normalized_blz,
            bic=normalized_bic,
            created_at=_utcnow(),
        )
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def preview_account(
        self,
        partner_id: UUID,
        mandant_id: UUID,
        account_number: str,
        blz: str | None = None,
    ) -> "AccountPreviewResponse":
        """Gibt alle Buchungszeilen zurück, die zu dieser Kontonummer passen,
        aber NICHT zum angegebenen Partner gehören."""
        from app.imports.models import JournalLine
        from app.partners.schemas import AccountPreviewLineItem, AccountPreviewResponse
        from decimal import Decimal

        await self.get_partner(partner_id, mandant_id)
        normalized_acct, _, _ = self._normalize_account_fields(account_number, blz)

        lines = (
            await self._session.exec(
                select(JournalLine)
                .where(
                    JournalLine.partner_account_raw == normalized_acct,
                )
            )
        ).all()

        # Fallback: auch nach blz-loser Übereinstimmung suchen (raw-Vergleich)
        if not lines:
            lines = (
                await self._session.exec(
                    select(JournalLine)
                    .where(
                        JournalLine.partner_account_raw.ilike(f"%{normalized_acct}%"),  # type: ignore[union-attr]
                    )
                )
            ).all()

        # Nur Zeilen desselben Mandanten
        from app.tenants.models import Account as _Account
        account_ids = set(
            (await self._session.exec(select(_Account.id).where(_Account.mandant_id == mandant_id))).all()
        )
        lines = [ln for ln in lines if ln.account_id in account_ids]

        partner_name_cache: dict[UUID | None, str | None] = {}
        service_name_cache: dict[UUID | None, str | None] = {None: None}
        partner_conflict_cache: dict[UUID, PartnerAssignmentCriteria] = {}
        matched: list[AccountPreviewLineItem] = []
        for line in lines:
            if line.partner_id not in partner_name_cache:
                if line.partner_id is None:
                    partner_name_cache[None] = None
                else:
                    p = await self._session.get(Partner, line.partner_id)
                    partner_name_cache[line.partner_id] = ((p.display_name or p.name) if p else None)
            if line.service_id not in service_name_cache:
                current_service = await self._session.get(Service, line.service_id)
                service_name_cache[line.service_id] = current_service.name if current_service else None
            conflict_reasons: list[str] = []
            if line.partner_id is not None and line.partner_id != partner_id:
                if line.partner_id not in partner_conflict_cache:
                    partner_conflict_cache[line.partner_id] = await load_partner_assignment_criteria(self._session, line.partner_id)
                conflict_reasons = detect_conflicting_criteria(partner_conflict_cache[line.partner_id], line)
            matched.append(AccountPreviewLineItem(
                journal_line_id=line.id,
                partner_name_raw=line.partner_name_raw,
                current_partner_name=partner_name_cache.get(line.partner_id),
                current_service_name=service_name_cache.get(line.service_id),
                has_conflicting_partner_criteria=bool(conflict_reasons),
                conflicting_partner_criteria=conflict_reasons,
                booking_date=line.booking_date,
                valuta_date=line.valuta_date,
                amount=Decimal(str(line.amount)),
                currency=line.currency,
                text=line.text,
                already_assigned=line.partner_id == partner_id,
            ))

        matched.sort(key=lambda x: x.booking_date, reverse=True)
        matched.sort(key=lambda x: not x.has_conflicting_partner_criteria)
        return AccountPreviewResponse(matched_lines=matched, total=len(matched))

    async def add_account_with_reassign(
        self,
        partner_id: UUID,
        mandant_id: UUID,
        account_number: str,
        blz: str | None = None,
        bic: str | None = None,
    ) -> PartnerAccount:
        """Speichert Kontonummer und weist passende Buchungszeilen dem Partner zu.
        Es werden nur die tatsächlich gematchten Zeilen verschoben;
        Source-Partner werden nur gelöscht, falls danach keine Zeilen mehr vorhanden sind."""
        from app.imports.models import JournalLine
        await self.get_partner(partner_id, mandant_id)
        normalized_acct, normalized_blz, normalized_bic = self._normalize_account_fields(account_number, blz, bic)
        await self._ensure_account_available(normalized_acct, normalized_blz)

        entity = PartnerAccount(
            partner_id=partner_id,
            account_number=normalized_acct,
            blz=normalized_blz,
            bic=normalized_bic,
            created_at=_utcnow(),
        )
        self._session.add(entity)
        await self._session.flush()

        # Buchungszeilen desselben Mandanten mit dieser Kontonummer suchen (nur fremde)
        from app.tenants.models import Account as _Account
        account_ids = set(
            (await self._session.exec(select(_Account.id).where(_Account.mandant_id == mandant_id))).all()
        )

        # NULL != UUID ergibt in SQL NULL (falsy) → explizit IS NULL einschließen
        not_this_partner = or_(
            JournalLine.partner_id != partner_id,
            JournalLine.partner_id.is_(None),  # type: ignore[union-attr]
        )
        matching_lines = (
            await self._session.exec(
                select(JournalLine)
                .where(
                    JournalLine.partner_account_raw == normalized_acct,
                    not_this_partner,
                )
            )
        ).all()
        if not matching_lines:
            matching_lines = (
                await self._session.exec(
                    select(JournalLine)
                    .where(
                        JournalLine.partner_account_raw.ilike(f"%{normalized_acct}%"),  # type: ignore[union-attr]
                        not_this_partner,
                    )
                )
            ).all()

        matching_lines = [ln for ln in matching_lines if ln.account_id in account_ids]

        # Zeilen ohne Partner direkt zuordnen; Zeilen fremder Partner nur selektiv verschieben
        unassigned_lines = [ln for ln in matching_lines if ln.partner_id is None]
        matching_by_partner: dict[UUID, list[JournalLine]] = {}
        for ln in matching_lines:
            if ln.partner_id is not None:
                matching_by_partner.setdefault(ln.partner_id, []).append(ln)

        svc_svc = ServiceManagementService(self._session)
        needs_revalidation = False

        # Zeilen ohne Partner: direkt diesem Partner zuweisen
        if unassigned_lines:
            await svc_svc.prepare_lines_for_partner_change(mandant_id, unassigned_lines, partner_id)
            needs_revalidation = True

        if matching_by_partner:
            for src_id, matched_lines in matching_by_partner.items():
                await svc_svc.prepare_lines_for_partner_change(mandant_id, list(matched_lines), partner_id)
                needs_revalidation = True

                # Source-Partner löschen wenn leer (wie Service-Matcher-Flow)
                remaining = (
                    await self._session.exec(
                        select(JournalLine.id).where(JournalLine.partner_id == src_id).limit(1)
                    )
                ).first()
                if remaining is None:
                    src_partner = await self._session.get(Partner, src_id)
                    if src_partner is not None and src_partner.mandant_id == mandant_id:
                        await delete_partner_clean(
                            self._session,
                            src_partner,
                            detach_journal_lines=False,
                        )

        if needs_revalidation:
            await svc_svc.revalidate_partner_lines(partner_id)
        else:
            await self._session.commit()

        await self._session.refresh(entity)
        return entity

    @staticmethod
    def _normalize_account_fields(
        account_number: str,
        blz: str | None = None,
        bic: str | None = None,
    ) -> tuple[str, str | None, str | None]:
        normalized_acct = account_number.strip().lstrip("0") or account_number.strip()
        normalized_blz = blz.strip() if blz else None
        normalized_bic = bic.strip().upper() if bic else None
        return normalized_acct, normalized_blz, normalized_bic

    async def _ensure_account_available(self, normalized_acct: str, normalized_blz: str | None) -> None:
        existing = await self._session.exec(
            select(PartnerAccount).where(
                PartnerAccount.account_number == normalized_acct,
                PartnerAccount.blz == normalized_blz,
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account number already assigned to another partner",
            )

    async def remove_account(self, account_id: UUID, partner_id: UUID, mandant_id: UUID) -> None:
        await self.get_partner(partner_id, mandant_id)  # verify ownership
        entity = await self._session.get(PartnerAccount, account_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        await self._session.delete(entity)
        await self._session.commit()

    async def add_name(self, partner_id: UUID, mandant_id: UUID, name: str) -> PartnerName:
        await self.get_partner(partner_id, mandant_id)  # verify ownership
        existing = await self._session.exec(
            select(PartnerName).where(
                PartnerName.partner_id == partner_id,
                PartnerName.name == name,
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Name already exists for this partner",
            )
        entity = PartnerName(partner_id=partner_id, name=name, created_at=_utcnow())
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def remove_name(self, name_id: UUID, partner_id: UUID, mandant_id: UUID) -> None:
        await self.get_partner(partner_id, mandant_id)  # verify ownership
        entity = await self._session.get(PartnerName, name_id)
        if entity is None or entity.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Name not found")
        await self._session.delete(entity)
        await self._session.commit()

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
        await self._transfer_accounts(source_id, target_id)
        await self._transfer_names(source_id, target_id)

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

        if lines_reassigned > 0:
            service_svc = ServiceManagementService(self._session)
            await service_svc.revalidate_partner_lines(target_id)
        else:
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

    async def _transfer_accounts(self, source_id: UUID, target_id: UUID) -> None:
        target_existing = (
            await self._session.exec(
                select(PartnerAccount.account_number).where(PartnerAccount.partner_id == target_id)
            )
        ).all()
        target_set = set(target_existing)

        source_accounts = (
            await self._session.exec(
                select(PartnerAccount).where(PartnerAccount.partner_id == source_id)
            )
        ).all()

        for pa in source_accounts:
            if pa.account_number in target_set:
                await self._session.delete(pa)
            else:
                pa.partner_id = target_id
                self._session.add(pa)

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

    async def _reassign_journal_lines(
        self, source_id: UUID, target_id: UUID, mandant_id: UUID
    ) -> int:
        try:
            from app.imports.models import JournalLine
            from app.tenants.models import Account as _Account
            service_svc = ServiceManagementService(self._session)

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

            return await service_svc.prepare_lines_for_partner_change(mandant_id, lines, target_id)
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
