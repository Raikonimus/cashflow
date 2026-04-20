import re
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.imports.models import JournalLine
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import Service, ServiceMatcher, ServiceMatcherType
from app.tenants.models import Account
from app.testing.schemas import (
    AssignmentMismatchItem,
    AssignmentTestJournalLine,
    PartnerAssignmentTestResponse,
    ServiceAmountConsistencyItem,
    ServiceAmountConsistencyLineStatusResponse,
    ServiceAmountConsistencyTestResponse,
)


def _normalize_iban(raw: str) -> str:
    return raw.replace(" ", "").upper()


def _normalize_account(raw: str) -> str:
    return raw.strip().lstrip("0") or raw.strip()


@dataclass
class ExpectedAssignment:
    outcome: str
    partner_id: UUID | None
    reason_text: str


class TestingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_service_amount_consistency_ok(
        self,
        mandant_id: UUID,
        line_id: UUID,
        *,
        is_ok: bool,
    ) -> ServiceAmountConsistencyLineStatusResponse:
        line = (
            await self._session.exec(
                select(JournalLine)
                .join(Account, Account.id == JournalLine.account_id)  # type: ignore[arg-type]
                .where(
                    JournalLine.id == line_id,
                    Account.mandant_id == mandant_id,
                )
            )
        ).first()

        if line is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Journal line not found",
            )

        line.service_amount_consistency_ok = is_ok
        self._session.add(line)
        await self._session.commit()
        await self._session.refresh(line)

        return ServiceAmountConsistencyLineStatusResponse(
            journal_line_id=line.id,
            service_amount_consistency_ok=line.service_amount_consistency_ok,
        )

    async def run_service_amount_consistency_test(
        self,
        mandant_id: UUID,
    ) -> ServiceAmountConsistencyTestResponse:
        account_ids = set(
            (
                await self._session.exec(
                    select(Account.id).where(Account.mandant_id == mandant_id)
                )
            ).all()
        )

        if not account_ids:
            return ServiceAmountConsistencyTestResponse(total_checked_services=0, inconsistent_services=[])

        lines = list(
            (
                await self._session.exec(
                    select(JournalLine).where(
                        sa.literal_column('journal_lines.account_id').in_(account_ids),
                        sa.literal_column('journal_lines.service_id').is_not(None),
                    )
                )
            ).all()
        )

        if not lines:
            return ServiceAmountConsistencyTestResponse(total_checked_services=0, inconsistent_services=[])

        service_ids = {line.service_id for line in lines if line.service_id is not None}
        services = list(
            (
                await self._session.exec(
                    select(Service, Partner)
                    .join(Partner, Partner.id == Service.partner_id)  # type: ignore[arg-type]
                    .where(sa.literal_column('services.id').in_(service_ids))
                )
            ).all()
        )
        service_meta_by_id = {
            service.id: {
                "service_name": service.name,
                "partner_id": partner.id,
                "partner_name": partner.display_name or partner.name,
            }
            for service, partner in services
            if service.id is not None
        }

        lines_by_service: dict[UUID, list[JournalLine]] = {}
        for line in lines:
            if line.service_id is None:
                continue
            lines_by_service.setdefault(line.service_id, []).append(line)

        inconsistent_services: list[ServiceAmountConsistencyItem] = []
        for service_id, service_lines in lines_by_service.items():
            relevant_lines = [
                line for line in service_lines if not line.service_amount_consistency_ok
            ]
            positive_count = sum(1 for line in relevant_lines if line.amount > 0)
            negative_count = sum(1 for line in relevant_lines if line.amount < 0)
            if positive_count == 0 or negative_count == 0:
                continue

            service_meta = service_meta_by_id.get(service_id)
            if service_meta is None:
                continue

            sorted_lines = sorted(
                service_lines,
                key=lambda line: (line.booking_date, line.valuta_date, str(line.id)),
                reverse=True,
            )
            inconsistent_services.append(
                ServiceAmountConsistencyItem(
                    service_id=service_id,
                    service_name=service_meta["service_name"],
                    partner_id=service_meta["partner_id"],
                    partner_name=service_meta["partner_name"],
                    positive_line_count=positive_count,
                    negative_line_count=negative_count,
                    lines=[AssignmentTestJournalLine.model_validate(line) for line in sorted_lines],
                )
            )

        inconsistent_services.sort(
            key=lambda item: (
                item.partner_name or "",
                item.service_name,
            )
        )

        return ServiceAmountConsistencyTestResponse(
            total_checked_services=len(lines_by_service),
            inconsistent_services=inconsistent_services,
        )

    async def run_partner_assignment_consistency_test(
        self,
        mandant_id: UUID,
    ) -> PartnerAssignmentTestResponse:
        account_ids = set(
            (
                await self._session.exec(
                    select(Account.id).where(Account.mandant_id == mandant_id)
                )
            ).all()
        )

        if not account_ids:
            return PartnerAssignmentTestResponse(total_checked=0, mismatches=[])

        lines = list(
            (
                await self._session.exec(
                    select(JournalLine).where(sa.literal_column('journal_lines.account_id').in_(account_ids))
                )
            ).all()
        )

        active_partners = list(
            (
                await self._session.exec(
                    select(Partner).where(
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                    )
                )
            ).all()
        )
        partner_name_by_id: dict[UUID, str] = {
            p.id: (p.display_name or p.name) for p in active_partners if p.id is not None
        }

        # IBAN and account are globally unique in this model.
        ibans = list(
            (
                await self._session.exec(
                    select(PartnerIban)
                    .join(Partner, Partner.id == PartnerIban.partner_id)  # type: ignore[arg-type]
                    .where(
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                    )
                )
            ).all()
        )
        partner_by_iban: dict[str, UUID] = {
            iban.iban: iban.partner_id for iban in ibans
        }

        accounts = list(
            (
                await self._session.exec(
                    select(PartnerAccount)
                    .join(Partner, Partner.id == PartnerAccount.partner_id)  # type: ignore[arg-type]
                    .where(
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                    )
                )
            ).all()
        )
        partner_by_account: dict[str, UUID] = {
            account.account_number: account.partner_id for account in accounts
        }

        # Name matching can have multiple hits -> treat as ambiguous when >1 partner fits.
        partner_names = list(
            (
                await self._session.exec(
                    select(PartnerName)
                    .join(Partner, Partner.id == PartnerName.partner_id)  # type: ignore[arg-type]
                    .where(
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                    )
                )
            ).all()
        )
        partner_ids_by_name: dict[str, set[UUID]] = {}
        for pn in partner_names:
            partner_ids_by_name.setdefault(pn.name.lower(), set()).add(pn.partner_id)

        # Fallback from Partner.name itself
        for p in active_partners:
            if p.id is None:
                continue
            partner_ids_by_name.setdefault(p.name.lower(), set()).add(p.id)

        services = list(
            (
                await self._session.exec(
                    select(Service)
                    .join(Partner, Partner.id == Service.partner_id)  # type: ignore[arg-type]
                    .where(
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                        Service.is_base_service == False,  # noqa: E712
                    )
                )
            ).all()
        )
        service_by_id: dict[UUID, Service] = {s.id: s for s in services if s.id is not None}

        matchers = list(
            (
                await self._session.exec(
                    select(ServiceMatcher)
                    .join(Service, Service.id == ServiceMatcher.service_id)  # type: ignore[arg-type]
                    .join(Partner, Partner.id == Service.partner_id)  # type: ignore[arg-type]
                    .where(
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                        Service.is_base_service == False,  # noqa: E712
                    )
                )
            ).all()
        )
        partner_matchers: dict[UUID, list[ServiceMatcher]] = {}
        for matcher in matchers:
            service = service_by_id.get(matcher.service_id)
            if service is None:
                continue
            partner_matchers.setdefault(service.partner_id, []).append(matcher)

        current_service_names = {
            s.id: s.name
            for s in (
                await self._session.exec(select(Service))
            ).all()
            if s.id is not None
        }

        mismatches: list[AssignmentMismatchItem] = []
        for line in lines:
            expected = self._expected_assignment_for_line(
                line=line,
                partner_by_iban=partner_by_iban,
                partner_by_account=partner_by_account,
                partner_ids_by_name=partner_ids_by_name,
                partner_matchers=partner_matchers,
                partner_name_by_id=partner_name_by_id,
            )

            mismatch = self._build_mismatch_if_needed(
                line=line,
                expected=expected,
                partner_name_by_id=partner_name_by_id,
                current_service_names=current_service_names,
            )
            if mismatch is not None:
                mismatches.append(mismatch)

        return PartnerAssignmentTestResponse(
            total_checked=len(lines),
            mismatches=mismatches,
        )

    def _expected_assignment_for_line(
        self,
        *,
        line: JournalLine,
        partner_by_iban: dict[str, UUID],
        partner_by_account: dict[str, UUID],
        partner_ids_by_name: dict[str, set[UUID]],
        partner_matchers: dict[UUID, list[ServiceMatcher]],
        partner_name_by_id: dict[UUID, str],
    ) -> ExpectedAssignment:
        if line.partner_iban_raw:
            normalized_iban = _normalize_iban(line.partner_iban_raw)
            partner_id = partner_by_iban.get(normalized_iban)
            if partner_id is not None:
                return ExpectedAssignment(
                    outcome="iban_match",
                    partner_id=partner_id,
                    reason_text=f"IBAN-Match auf {normalized_iban}",
                )

        if line.partner_account_raw:
            normalized_account = _normalize_account(line.partner_account_raw)
            partner_id = partner_by_account.get(normalized_account)
            if partner_id is not None:
                return ExpectedAssignment(
                    outcome="account_match",
                    partner_id=partner_id,
                    reason_text=f"Kontonummer-Match auf {normalized_account}",
                )

        if line.partner_name_raw:
            name_ids = list(partner_ids_by_name.get(line.partner_name_raw.lower(), set()))
            if len(name_ids) == 1:
                return ExpectedAssignment(
                    outcome="name_match",
                    partner_id=name_ids[0],
                    reason_text=f"Name-Match auf {line.partner_name_raw}",
                )
            if len(name_ids) > 1:
                return ExpectedAssignment(
                    outcome="name_ambiguous",
                    partner_id=None,
                    reason_text=f"Name-Match ist mehrdeutig ({len(name_ids)} Partner)",
                )

        searchable = "\n".join(filter(None, [line.text or "", line.partner_name_raw or ""]))
        searchable_lower = searchable.lower()
        service_matched_partners: list[UUID] = []
        for partner_id, matchers in partner_matchers.items():
            if self._any_matcher_hits(matchers, searchable, searchable_lower):
                service_matched_partners.append(partner_id)

        if len(service_matched_partners) == 1:
            partner_id = service_matched_partners[0]
            return ExpectedAssignment(
                outcome="service_matcher_match",
                partner_id=partner_id,
                reason_text=f"Leistungs-Matcher-Match auf {partner_name_by_id.get(partner_id, str(partner_id))}",
            )
        if len(service_matched_partners) > 1:
            return ExpectedAssignment(
                outcome="service_matcher_ambiguous",
                partner_id=None,
                reason_text=f"Leistungs-Matcher mehrdeutig ({len(service_matched_partners)} Partner)",
            )

        if not line.partner_name_raw:
            return ExpectedAssignment(
                outcome="no_partner_identified",
                partner_id=None,
                reason_text="Kein Partnername vorhanden und keine Regel greift",
            )

        return ExpectedAssignment(
            outcome="new_partner",
            partner_id=None,
            reason_text=f"Würde als neuer Partner angelegt werden ({line.partner_name_raw})",
        )

    def _build_mismatch_if_needed(
        self,
        *,
        line: JournalLine,
        expected: ExpectedAssignment,
        partner_name_by_id: dict[UUID, str],
        current_service_names: dict[UUID, str],
    ) -> AssignmentMismatchItem | None:
        current_partner_id = line.partner_id

        if current_partner_id is None:
            if expected.partner_id is None:
                return None
            return AssignmentMismatchItem(
                reason_code="unassigned_but_expected_partner",
                reason_text=(
                    f"Unzugeordnet, aber Regel erwartet Partner {partner_name_by_id.get(expected.partner_id, str(expected.partner_id))}"
                ),
                expected_outcome=expected.outcome,
                expected_partner_id=expected.partner_id,
                expected_partner_name=partner_name_by_id.get(expected.partner_id),
                current_partner_id=None,
                current_partner_name=None,
                current_service_id=line.service_id,
                current_service_name=current_service_names.get(line.service_id) if line.service_id else None,
                journal_line=AssignmentTestJournalLine.model_validate(line.model_dump()),
            )

        if expected.partner_id == current_partner_id:
            return None

        if expected.partner_id is None:
            return AssignmentMismatchItem(
                reason_code="assigned_but_not_explainable",
                reason_text=f"Zuordnung zu {partner_name_by_id.get(current_partner_id, str(current_partner_id))} ist durch keine Regel eindeutig erklärbar ({expected.reason_text})",
                expected_outcome=expected.outcome,
                expected_partner_id=None,
                expected_partner_name=None,
                current_partner_id=current_partner_id,
                current_partner_name=partner_name_by_id.get(current_partner_id),
                current_service_id=line.service_id,
                current_service_name=current_service_names.get(line.service_id) if line.service_id else None,
                journal_line=AssignmentTestJournalLine.model_validate(line.model_dump()),
            )

        return AssignmentMismatchItem(
            reason_code="assigned_to_different_partner",
            reason_text=(
                "Aktueller Partner weicht von den Zuordnungskriterien ab "
                f"(erwartet: {partner_name_by_id.get(expected.partner_id, str(expected.partner_id))}, "
                f"aktuell: {partner_name_by_id.get(current_partner_id, str(current_partner_id))})"
            ),
            expected_outcome=expected.outcome,
            expected_partner_id=expected.partner_id,
            expected_partner_name=partner_name_by_id.get(expected.partner_id),
            current_partner_id=current_partner_id,
            current_partner_name=partner_name_by_id.get(current_partner_id),
            current_service_id=line.service_id,
            current_service_name=current_service_names.get(line.service_id) if line.service_id else None,
            journal_line=AssignmentTestJournalLine.model_validate(line.model_dump()),
        )

    @staticmethod
    def _any_matcher_hits(
        matchers: list[ServiceMatcher],
        searchable: str,
        searchable_lower: str,
    ) -> bool:
        for matcher in matchers:
            if matcher.pattern_type == ServiceMatcherType.string.value:
                if matcher.pattern.lower() in searchable_lower:
                    return True
                continue
            try:
                if re.search(matcher.pattern, searchable, re.IGNORECASE):
                    return True
            except re.error:
                # Invalid regex should not crash diagnostics; just ignore this matcher.
                continue
        return False
