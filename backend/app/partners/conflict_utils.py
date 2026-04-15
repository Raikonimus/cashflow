import re
from dataclasses import dataclass
from uuid import UUID

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.imports.models import JournalLine
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import Service, ServiceMatcher, ServiceMatcherType


@dataclass
class PartnerAssignmentCriteria:
    ibans: set[str]
    accounts: set[str]
    names_lower: set[str]
    service_matchers: list[ServiceMatcher]


def normalize_iban(raw: str) -> str:
    return raw.replace(" ", "").upper()


def normalize_account(raw: str) -> str:
    normalized = raw.strip()
    return normalized.lstrip("0") or normalized


async def load_partner_assignment_criteria(
    session: AsyncSession,
    partner_id: UUID,
) -> PartnerAssignmentCriteria:
    ibans = set((await session.exec(select(PartnerIban.iban).where(PartnerIban.partner_id == partner_id))).all())
    accounts = set((await session.exec(select(PartnerAccount.account_number).where(PartnerAccount.partner_id == partner_id))).all())

    names = set((await session.exec(select(PartnerName.name).where(PartnerName.partner_id == partner_id))).all())
    partner = await session.get(Partner, partner_id)
    if partner is not None:
        names.add(partner.name)

    service_matchers = (
        await session.exec(
            select(ServiceMatcher)
            .join(Service, Service.id == ServiceMatcher.service_id)
            .where(Service.partner_id == partner_id, Service.is_base_service == False)  # noqa: E712
        )
    ).all()

    return PartnerAssignmentCriteria(
        ibans=ibans,
        accounts=accounts,
        names_lower={name.lower() for name in names if name},
        service_matchers=service_matchers,
    )


def detect_conflicting_criteria(criteria: PartnerAssignmentCriteria, line: JournalLine) -> list[str]:
    reasons: list[str] = []

    if line.partner_iban_raw:
        normalized_iban = normalize_iban(line.partner_iban_raw)
        if normalized_iban in criteria.ibans:
            reasons.append("iban")

    if line.partner_account_raw:
        normalized_account = normalize_account(line.partner_account_raw)
        if normalized_account in criteria.accounts:
            reasons.append("account")

    if line.partner_name_raw and line.partner_name_raw.lower() in criteria.names_lower:
        reasons.append("name")

    searchable = "\n".join(filter(None, [line.text or "", line.partner_name_raw or ""]))
    searchable_lower = searchable.lower()
    if searchable and _service_matchers_hit(criteria.service_matchers, searchable, searchable_lower):
        reasons.append("service_matcher")

    return reasons


def _service_matchers_hit(matchers: list[ServiceMatcher], searchable: str, searchable_lower: str) -> bool:
    for matcher in matchers:
        if matcher.pattern_type == ServiceMatcherType.string.value:
            if matcher.pattern.lower() in searchable_lower:
                return True
            continue
        try:
            if re.search(matcher.pattern, searchable, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False
