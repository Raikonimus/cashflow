from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.imports.models import JournalLine, JournalLineSplit, ReviewItem
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import Service, ServiceMatcher


async def delete_partner_clean(
    session: AsyncSession,
    partner: Partner,
    *,
    detach_journal_lines: bool,
) -> None:
    """Delete a partner and all dependent records without leaving orphans.

    If journal lines still reference the partner:
    - detach_journal_lines=False -> raise 409
    - detach_journal_lines=True -> clear partner/service assignments on those lines
    """
    partner_id = partner.id
    if partner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")

    service_ids = list(
        (
            await session.exec(
                select(Service.id).where(Service.partner_id == partner_id)
            )
        ).all()
    )

    journal_lines = list(
        (
            await session.exec(
                select(JournalLine).where(JournalLine.partner_id == partner_id)
            )
        ).all()
    )

    if journal_lines and not detach_journal_lines:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Partner has journal entries. Move the bookings first before deleting this partner.",
        )

    if journal_lines:
        for line in journal_lines:
            line.partner_id = None
            session.add(line)
        line_ids = [line.id for line in journal_lines if line.id is not None]
        if line_ids:
            await session.exec(  # type: ignore[attr-defined]
                delete(JournalLineSplit).where(JournalLineSplit.journal_line_id.in_(line_ids))  # type: ignore[attr-defined]
            )

    if service_ids:
        # Splits löschen, die auf diese Services verweisen
        await session.exec(  # type: ignore[attr-defined]
            delete(JournalLineSplit).where(JournalLineSplit.service_id.in_(service_ids))  # type: ignore[attr-defined]
        )
        await session.exec(delete(ReviewItem).where(ReviewItem.service_id.in_(service_ids)))
        await session.exec(delete(ServiceMatcher).where(ServiceMatcher.service_id.in_(service_ids)))
        await session.exec(delete(Service).where(Service.id.in_(service_ids)))

    await session.exec(delete(PartnerIban).where(PartnerIban.partner_id == partner_id))
    await session.exec(delete(PartnerAccount).where(PartnerAccount.partner_id == partner_id))
    await session.exec(delete(PartnerName).where(PartnerName.partner_id == partner_id))

    await session.delete(partner)
    await session.flush()
