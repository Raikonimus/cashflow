"""ReviewService — confirm, reassign, new-partner actions for ReviewItems."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.imports.models import JournalLine, ReviewItem, utcnow
from app.partners.models import AuditLog, Partner, PartnerIban
from app.review.schemas import (
    AdjustReviewRequest,
    ReviewItemResponse,
    ReviewJournalLineSummary,
    ReviewServiceSummary,
)
from app.services.models import Service, ServiceType
from app.services.service import ServiceManagementService, _default_tax_rate

log = structlog.get_logger()

_IBAN_NORM = str.maketrans("", "", " ")


def _normalize_iban(raw: str) -> str:
    return raw.translate(_IBAN_NORM).upper()


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def list_items(
        self,
        mandant_id: UUID,
        status_filter: str | None,
        item_type: str | None,
        page: int,
        size: int,
    ) -> tuple[list[ReviewItem], int]:
        size = min(size, 100)

        base_where = [ReviewItem.mandant_id == mandant_id]
        if status_filter and status_filter != "all":
            base_where.append(ReviewItem.status == status_filter)
        if item_type:
            base_where.append(ReviewItem.item_type == item_type)

        items = list(
            (
                await self._session.exec(  # type: ignore[attr-defined]
                    select(ReviewItem)
                    .where(*base_where)
                    .order_by(col(ReviewItem.created_at))
                )
            ).all()
        )

        items = [item for item in items if not self._should_hide_from_open_list(item, status_filter)]
        total = len(items)
        offset = (page - 1) * size

        return items[offset:offset + size], total

    async def get_item(self, item_id: UUID, mandant_id: UUID) -> ReviewItem:
        item = await self._session.get(ReviewItem, item_id)
        if item is None or item.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found")
        return item

    async def list_archive(
        self,
        mandant_id: UUID,
        item_type: str | None,
        resolved_by_user_id: UUID | None,
        resolved_from: date | None,
        resolved_to: date | None,
        page: int,
        size: int,
    ) -> tuple[list[ReviewItem], int]:
        size = min(size, 100)
        offset = (page - 1) * size

        base_where = [
            ReviewItem.mandant_id == mandant_id,
            or_(
                ReviewItem.status == "confirmed",  # type: ignore[operator]
                ReviewItem.status == "adjusted",  # type: ignore[operator]
                ReviewItem.status == "rejected",  # type: ignore[operator]
            ),
            ReviewItem.resolved_at != None,  # noqa: E711  # type: ignore[comparison-overlap]
        ]
        if item_type:
            base_where.append(ReviewItem.item_type == item_type)
        if resolved_by_user_id is not None:
            base_where.append(ReviewItem.resolved_by == resolved_by_user_id)
        if resolved_from is not None:
            base_where.append(ReviewItem.resolved_at >= datetime.combine(resolved_from, time.min, tzinfo=timezone.utc))
        if resolved_to is not None:
            base_where.append(ReviewItem.resolved_at <= datetime.combine(resolved_to, time.max, tzinfo=timezone.utc))

        total = len(
            (
                await self._session.exec(
                    select(ReviewItem.id).where(*base_where)  # type: ignore[arg-type]
                )
            ).all()
        )

        items = list(
            (
                await self._session.exec(
                    select(ReviewItem)
                    .where(*base_where)
                    .order_by(desc(ReviewItem.resolved_at), desc(ReviewItem.created_at))
                    .offset(offset)
                    .limit(size)
                )
            ).all()
        )

        return items, total

    async def to_response(self, item: ReviewItem) -> ReviewItemResponse:
        journal_line = await self._load_journal_line_summary(item.journal_line_id)
        service = await self._load_service_summary(item.service_id)
        context = await self._enrich_context(item.context)
        assigned_journal_lines: list[ReviewJournalLineSummary] = []
        if item.item_type == "service_type_review" and item.service_id is not None:
            lines = (
                await self._session.exec(
                    select(JournalLine)
                    .where(JournalLine.service_id == item.service_id)
                    .order_by(JournalLine.created_at)
                )
            ).all()
            assigned_journal_lines = [await self._serialize_journal_line(line) for line in lines]

        return ReviewItemResponse(
            id=item.id,
            mandant_id=item.mandant_id,
            item_type=item.item_type,
            journal_line_id=item.journal_line_id,
            service_id=item.service_id,
            context=context,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
            resolved_by=item.resolved_by,
            resolved_at=item.resolved_at,
            journal_line=journal_line,
            service=service,
            assigned_journal_lines=assigned_journal_lines,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def confirm(
        self, item_id: UUID, mandant_id: UUID, actor_id: UUID
    ) -> ReviewItem:
        item = await self._get_open_or_raise(item_id, mandant_id)

        if item.item_type == "service_assignment":
            return await self._confirm_service_assignment(item, mandant_id, actor_id)
        if item.item_type == "service_type_review":
            return await self._confirm_service_type_review(item, mandant_id, actor_id)

        journal_line = await self._session.get(JournalLine, item.journal_line_id)
        if journal_line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        # ADR-013: register IBAN automatically when confirming
        if journal_line.partner_iban_raw and journal_line.partner_id:
            normalized = _normalize_iban(journal_line.partner_iban_raw)
            existing_iban = (
                await self._session.exec(  # type: ignore[attr-defined]
                    select(PartnerIban).where(PartnerIban.iban == normalized)
                )
            ).first()
            if existing_iban is None:
                self._session.add(
                    PartnerIban(
                        partner_id=journal_line.partner_id,
                        iban=normalized,
                        created_at=utcnow(),
                    )
                )

        item.status = "confirmed"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.confirmed",
                actor_id=actor_id,
                payload={
                    "item_id": str(item_id),
                    "journal_line_id": str(item.journal_line_id),
                    "partner_id": str(journal_line.partner_id),
                },
            )
        )

        await self._session.commit()
        await self._session.refresh(item)
        log.info("review_confirmed", item_id=str(item_id), actor_id=str(actor_id))
        return item

    async def adjust(
        self,
        item_id: UUID,
        mandant_id: UUID,
        actor_id: UUID,
        body: AdjustReviewRequest,
    ) -> ReviewItem:
        item = await self._get_open_or_raise(item_id, mandant_id)

        if item.item_type == "service_assignment":
            if body.service_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="service_id is required for service assignment reviews")
            return await self._adjust_service_assignment(item, mandant_id, actor_id, body.service_id)

        if item.item_type == "service_type_review":
            if body.service_type is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="service_type is required for service type reviews")
            return await self._adjust_service_type_review(item, mandant_id, actor_id, body.service_type, body.tax_rate)

        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Adjust is not supported for this review item type")

    async def reject(self, item_id: UUID, mandant_id: UUID, actor_id: UUID) -> ReviewItem:
        item = await self._get_open_or_raise(item_id, mandant_id)
        item.status = "rejected"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.rejected",
                actor_id=actor_id,
                payload={
                    "item_id": str(item.id),
                    "item_type": item.item_type,
                },
            )
        )

        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def reassign(
        self, item_id: UUID, mandant_id: UUID, actor_id: UUID, partner_id: UUID
    ) -> ReviewItem:
        item = await self._get_open_or_raise(item_id, mandant_id)
        service_svc = ServiceManagementService(self._session)

        target = await self._session.get(Partner, partner_id)
        if target is None or target.mandant_id != mandant_id or not target.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")

        journal_line = await self._session.get(JournalLine, item.journal_line_id)
        if journal_line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        old_partner_id = journal_line.partner_id

        item.status = "adjusted"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.reassigned",
                actor_id=actor_id,
                payload={
                    "item_id": str(item_id),
                    "old_partner_id": str(old_partner_id),
                    "new_partner_id": str(partner_id),
                },
            )
        )

        await service_svc.prepare_lines_for_partner_change(mandant_id, [journal_line], partner_id)
        await service_svc.revalidate_partner_lines(partner_id)

        # Für new_partner-Items: Ghost-Partner löschen, wenn er nach der Neuzuweisung keine
        # Buchungszeilen mehr hat (automatisch angelegter Partner war fehlerhaft).
        if (
            item.item_type == "new_partner"
            and old_partner_id is not None
            and old_partner_id != partner_id
        ):
            remaining = (
                await self._session.exec(
                    select(JournalLine).where(JournalLine.partner_id == old_partner_id)
                )
            ).all()
            if not remaining:
                ghost = await self._session.get(Partner, old_partner_id)
                if ghost is not None and ghost.mandant_id == mandant_id:
                    await self._session.delete(ghost)
                    await self._session.commit()

        await self._session.refresh(item)
        log.info("review_reassigned", item_id=str(item_id), partner_id=str(partner_id))
        return item

    async def create_and_assign(
        self, item_id: UUID, mandant_id: UUID, actor_id: UUID, partner_name: str
    ) -> ReviewItem:
        item = await self._get_open_or_raise(item_id, mandant_id)
        service_svc = ServiceManagementService(self._session)

        journal_line = await self._session.get(JournalLine, item.journal_line_id)
        if journal_line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        # Guard name uniqueness (same pattern as matching.py)
        desired_name = partner_name
        existing = (
            await self._session.exec(  # type: ignore[attr-defined]
                select(Partner).where(
                    Partner.mandant_id == mandant_id,
                    Partner.name == desired_name,
                )
            )
        ).first()
        if existing is not None:
            desired_name = f"{desired_name} [{str(uuid4())[:8]}]"

        new_partner = Partner(
            id=uuid4(),
            mandant_id=mandant_id,
            name=desired_name,
            is_active=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self._session.add(new_partner)
        await self._session.flush()

        from app.services.service import ensure_base_service

        await ensure_base_service(self._session, new_partner.id)

        item.status = "adjusted"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.new_partner_assigned",
                actor_id=actor_id,
                payload={
                    "item_id": str(item_id),
                    "new_partner_id": str(new_partner.id),
                    "partner_name": desired_name,
                },
            )
        )

        await service_svc.prepare_lines_for_partner_change(mandant_id, [journal_line], new_partner.id)  # type: ignore[list-item]
        await service_svc.revalidate_partner_lines(new_partner.id)
        await self._session.refresh(item)
        log.info("review_new_partner", item_id=str(item_id), partner_name=desired_name)
        return item

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_open_or_raise(self, item_id: UUID, mandant_id: UUID) -> ReviewItem:
        item = await self._session.get(ReviewItem, item_id)
        if item is None or item.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found")
        if item.status != "open":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Review item is already {item.status}",
            )
        return item

    async def _confirm_service_assignment(
        self,
        item: ReviewItem,
        mandant_id: UUID,
        actor_id: UUID,
    ) -> ReviewItem:
        if item.journal_line_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        journal_line = await self._session.get(JournalLine, item.journal_line_id)
        if journal_line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        target_service_id = self._parse_optional_uuid(item.context.get("proposed_service_id"))
        if target_service_id is None:
            target_service_id = self._parse_optional_uuid(item.context.get("current_service_id")) or journal_line.service_id
        if target_service_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No target service available for confirmation")

        item.status = "confirmed"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)
        await self._session.flush()

        service_svc = ServiceManagementService(self._session)
        await service_svc.manually_assign_journal_line(mandant_id, journal_line, target_service_id)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.confirmed",
                actor_id=actor_id,
                payload={
                    "item_id": str(item.id),
                    "item_type": item.item_type,
                    "journal_line_id": str(journal_line.id),
                    "service_id": str(target_service_id),
                },
            )
        )

        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def _adjust_service_assignment(
        self,
        item: ReviewItem,
        mandant_id: UUID,
        actor_id: UUID,
        service_id: UUID,
    ) -> ReviewItem:
        if item.journal_line_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        journal_line = await self._session.get(JournalLine, item.journal_line_id)
        if journal_line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        previous_service_id = journal_line.service_id

        item.status = "adjusted"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)
        await self._session.flush()

        service_svc = ServiceManagementService(self._session)
        await service_svc.manually_assign_journal_line(mandant_id, journal_line, service_id)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.adjusted",
                actor_id=actor_id,
                payload={
                    "item_id": str(item.id),
                    "item_type": item.item_type,
                    "journal_line_id": str(journal_line.id),
                    "old_service_id": str(previous_service_id) if previous_service_id else None,
                    "new_service_id": str(service_id),
                },
            )
        )

        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def _confirm_service_type_review(
        self,
        item: ReviewItem,
        mandant_id: UUID,
        actor_id: UUID,
    ) -> ReviewItem:
        service = await self._get_service_for_review(item, mandant_id)
        auto_assigned_type = item.context.get("auto_assigned_type")
        if auto_assigned_type is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Review item is missing auto_assigned_type")

        resolved_type = ServiceType(auto_assigned_type)
        service.service_type = resolved_type.value
        service.service_type_manual = True
        if not service.tax_rate_manual:
            service.tax_rate = _default_tax_rate(resolved_type)
        service.updated_at = utcnow()
        self._session.add(service)

        item.status = "confirmed"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.confirmed",
                actor_id=actor_id,
                payload={
                    "item_id": str(item.id),
                    "item_type": item.item_type,
                    "service_id": str(service.id),
                },
            )
        )

        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def _adjust_service_type_review(
        self,
        item: ReviewItem,
        mandant_id: UUID,
        actor_id: UUID,
        service_type: ServiceType,
        tax_rate: Decimal | None,
    ) -> ReviewItem:
        service = await self._get_service_for_review(item, mandant_id)
        service.service_type = service_type.value
        service.service_type_manual = True
        if tax_rate is not None:
            service.tax_rate = tax_rate
            service.tax_rate_manual = True
        service.updated_at = utcnow()
        self._session.add(service)

        item.status = "adjusted"
        item.resolved_by = actor_id
        item.resolved_at = utcnow()
        item.updated_at = utcnow()
        self._session.add(item)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="review.adjusted",
                actor_id=actor_id,
                payload={
                    "item_id": str(item.id),
                    "item_type": item.item_type,
                    "service_id": str(service.id),
                    "service_type": service.service_type,
                    "tax_rate": str(service.tax_rate),
                },
            )
        )

        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def _load_journal_line_summary(
        self,
        journal_line_id: UUID | None,
    ) -> ReviewJournalLineSummary | None:
        if journal_line_id is None:
            return None
        journal_line = await self._session.get(JournalLine, journal_line_id)
        if journal_line is None:
            return None
        return await self._serialize_journal_line(journal_line)

    async def _load_service_summary(self, service_id: UUID | None) -> ReviewServiceSummary | None:
        if service_id is None:
            return None
        service = await self._session.get(Service, service_id)
        if service is None:
            return None
        partner = await self._session.get(Partner, service.partner_id)
        partner_name = None if partner is None else partner.display_name or partner.name
        return ReviewServiceSummary.model_validate(
            {
                "id": service.id,
                "partner_id": service.partner_id,
                "partner_name": partner_name,
                "name": service.name,
                "service_type": service.service_type,
                "tax_rate": service.tax_rate,
                "valid_from": service.valid_from,
                "valid_to": service.valid_to,
                "service_type_manual": service.service_type_manual,
                "tax_rate_manual": service.tax_rate_manual,
            }
        )

    async def _serialize_journal_line(self, line: JournalLine) -> ReviewJournalLineSummary:
        partner_name: str | None = None
        if line.partner_id is not None:
            partner = await self._session.get(Partner, line.partner_id)
            if partner is not None:
                partner_name = partner.display_name or partner.name

        return ReviewJournalLineSummary.model_validate(
            {
                "id": line.id,
                "partner_id": line.partner_id,
                "partner_name": partner_name,
                "service_id": line.service_id,
                "service_assignment_mode": line.service_assignment_mode,
                "valuta_date": line.valuta_date,
                "booking_date": line.booking_date,
                "amount": line.amount,
                "currency": line.currency,
                "text": line.text,
                "partner_name_raw": line.partner_name_raw,
            }
        )

    async def _enrich_context(self, raw_context: object) -> dict:
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        current_service_id = self._parse_optional_uuid(context.get("current_service_id"))
        proposed_service_id = self._parse_optional_uuid(context.get("proposed_service_id"))

        if current_service_id is not None:
            current_service = await self._session.get(Service, current_service_id)
            if current_service is not None:
                context["current_service_name"] = current_service.name

        if proposed_service_id is not None:
            proposed_service = await self._session.get(Service, proposed_service_id)
            if proposed_service is not None:
                context["proposed_service_name"] = proposed_service.name

        raw_matching_services = context.get("matching_services")
        if isinstance(raw_matching_services, list):
            matching_service_names: list[str] = []
            for raw_service_id in raw_matching_services:
                service_id = self._parse_optional_uuid(raw_service_id)
                if service_id is None:
                    continue
                service = await self._session.get(Service, service_id)
                if service is not None:
                    matching_service_names.append(service.name)
            if matching_service_names:
                context["matching_service_names"] = matching_service_names

        return context

    async def _get_service_for_review(self, item: ReviewItem, mandant_id: UUID) -> Service:
        if item.service_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        service = await self._session.get(Service, item.service_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

        partner = await self._session.get(Partner, service.partner_id)
        if partner is None or partner.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        return service

    def _parse_optional_uuid(self, raw_value: object) -> UUID | None:
        if raw_value in (None, ""):
            return None
        if isinstance(raw_value, UUID):
            return raw_value
        return UUID(str(raw_value))

    def _should_hide_from_open_list(self, item: ReviewItem, status_filter: str | None) -> bool:
        if status_filter != "open":
            return False
        if item.item_type != "service_type_review":
            return False
        context = item.context if isinstance(item.context, dict) else {}
        previous_type = context.get("previous_type")
        auto_assigned_type = context.get("auto_assigned_type")
        current_journal_line_ids = context.get("current_journal_line_ids")

        has_line_ids = isinstance(current_journal_line_ids, list) and len(current_journal_line_ids) > 0
        has_meaningful_types = previous_type not in (None, "") or auto_assigned_type not in (None, "")

        return not has_line_ids and not has_meaningful_types
