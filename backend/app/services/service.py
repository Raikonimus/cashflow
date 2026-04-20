import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.imports.models import JournalLine, ReviewItem
from app.partners.conflict_utils import PartnerAssignmentCriteria, detect_conflicting_criteria, load_partner_assignment_criteria
from app.partners.delete_utils import delete_partner_clean
from app.partners.models import Partner
from app.services.models import (
    BASE_SERVICE_NAME,
    KeywordTargetType,
    Service,
    ServiceGroup,
    ServiceGroupAssignment,
    ServiceGroupSection,
    ServiceMatcher,
    ServiceMatcherType,
    ServiceType,
    ServiceTypeKeyword,
)
from app.services.schemas import (
    CreateServiceMatcherRequest,
    CreateServiceRequest,
    CreateServiceGroupRequest,
    CreateServiceTypeKeywordRequest,
    DeleteServiceGroupRequest,
    MatcherPreviewLineItem,
    MatcherPreviewResponse,
    ServiceGroupAssignmentResponse,
    ServiceGroupResponse,
    ServiceResponse,
    ServiceTypeKeywordListResponse,
    ServiceTypeKeywordResponse,
    SystemServiceTypeKeywordResponse,
    UpdateServiceGroupRequest,
    UpdateServiceMatcherRequest,
    UpdateServiceRequest,
    UpdateServiceTypeKeywordRequest,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


SYSTEM_DEFAULT_KEYWORDS: tuple[SystemServiceTypeKeywordResponse, ...] = (
    SystemServiceTypeKeywordResponse(pattern="gehalt", pattern_type=ServiceMatcherType.string, target_service_type=KeywordTargetType.employee),
    SystemServiceTypeKeywordResponse(pattern="lohn", pattern_type=ServiceMatcherType.string, target_service_type=KeywordTargetType.employee),
    SystemServiceTypeKeywordResponse(pattern="entnahme", pattern_type=ServiceMatcherType.string, target_service_type=KeywordTargetType.shareholder),
    SystemServiceTypeKeywordResponse(pattern="steuer", pattern_type=ServiceMatcherType.string, target_service_type=KeywordTargetType.authority),
    SystemServiceTypeKeywordResponse(pattern="köst", pattern_type=ServiceMatcherType.string, target_service_type=KeywordTargetType.authority),
    SystemServiceTypeKeywordResponse(pattern="umsatzsteuer", pattern_type=ServiceMatcherType.string, target_service_type=KeywordTargetType.authority),
)

DEFAULT_GROUPS_BY_SECTION: dict[ServiceGroupSection, tuple[str, ...]] = {
    ServiceGroupSection.income: ("Kunden",),
    ServiceGroupSection.expense: ("Lieferanten", "Behörden", "Gesellschafter", "Mitarbeiter"),
    ServiceGroupSection.neutral: ("Erfolgsneutrale Zahlungen",),
}

DEFAULT_GROUP_BY_SERVICE_TYPE: dict[str, str] = {
    ServiceType.customer.value: "Kunden",
    ServiceType.supplier.value: "Lieferanten",
    ServiceType.authority.value: "Behörden",
    ServiceType.shareholder.value: "Gesellschafter",
    ServiceType.employee.value: "Mitarbeiter",
}

_EXPENSE_SERVICE_TYPES = {
    ServiceType.supplier.value,
    ServiceType.authority.value,
    ServiceType.shareholder.value,
    ServiceType.employee.value,
}


def _default_tax_rate(service_type: ServiceType) -> Decimal:
    if service_type in (ServiceType.employee, ServiceType.shareholder, ServiceType.authority):
        return Decimal("0.00")
    return Decimal("20.00")


@dataclass
class ServiceAssignmentResult:
    service_id: UUID
    matching_service_ids: list[UUID]
    reason: str


async def ensure_base_service(session: AsyncSession, partner_id: UUID) -> Service:
    existing = (
        await session.exec(
            select(Service).where(Service.partner_id == partner_id, Service.is_base_service == True)  # noqa: E712
        )
    ).first()
    if existing is not None:
        return existing

    base_service = Service(
        partner_id=partner_id,
        name=BASE_SERVICE_NAME,
        description=None,
        service_type=ServiceType.unknown.value,
        tax_rate=_default_tax_rate(ServiceType.unknown),
        erfolgsneutral=False,
        is_base_service=True,
        service_type_manual=False,
        tax_rate_manual=False,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(base_service)
    await session.flush()
    return base_service


class ServiceManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prepare_lines_for_partner_change(
        self,
        mandant_id: UUID,
        lines: list[JournalLine],
        new_partner_id: UUID,
    ) -> int:
        if not lines:
            return 0

        changed_line_ids: list[UUID] = []
        old_service_ids: set[UUID] = set()

        for line in lines:
            changed_line_ids.append(line.id)
            if line.service_id is not None:
                old_service_ids.add(line.service_id)
            line.partner_id = new_partner_id
            line.service_id = None
            line.service_assignment_mode = None
            self._session.add(line)

        await self._delete_open_line_reviews(changed_line_ids)
        await self._session.flush()

        for service_id in old_service_ids:
            await self.detect_service_type_for_service(mandant_id, service_id)

        return len(changed_line_ids)

    async def list_services(self, partner_id: UUID, mandant_id: UUID) -> list[ServiceResponse]:
        await self._get_partner(partner_id, mandant_id)
        services = (
            await self._session.exec(
                select(Service).where(Service.partner_id == partner_id).order_by(desc(Service.is_base_service), Service.name)
            )
        ).all()
        return [await self._to_response(service) for service in services]

    async def create_service(self, partner_id: UUID, mandant_id: UUID, body: CreateServiceRequest) -> ServiceResponse:
        await self._get_partner(partner_id, mandant_id)
        await self._ensure_unique_service_name(partner_id, body.name)
        await self.ensure_default_groups(mandant_id)
        now = _utcnow()
        service = Service(
            partner_id=partner_id,
            name=body.name,
            description=body.description,
            service_type=body.service_type.value,
            tax_rate=body.tax_rate,
            erfolgsneutral=body.erfolgsneutral,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            service_type_manual=True,
            tax_rate_manual=True,
            created_at=now,
            updated_at=now,
        )
        self._session.add(service)
        await self._session.flush()
        await self.ensure_service_group_assignment(mandant_id, service)
        await self._session.commit()
        await self._session.refresh(service)
        await self.detect_service_type_for_service(mandant_id, service.id)
        await self._trigger_revalidation(partner_id)
        return await self._to_response(service)

    async def update_service(self, service_id: UUID, mandant_id: UUID, body: UpdateServiceRequest) -> ServiceResponse:
        service = await self._get_service(service_id, mandant_id)
        refresh_group_assignment = False
        if service.is_base_service and body.name is not None and body.name != service.name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Base service name cannot be changed")
        if body.name is not None and body.name != service.name:
            await self._ensure_unique_service_name(service.partner_id, body.name, exclude_service_id=service.id)
            service.name = body.name
        if body.description is not None or "description" in body.model_fields_set:
            service.description = body.description
        if body.service_type is not None:
            service.service_type = body.service_type.value
            refresh_group_assignment = True
        if body.tax_rate is not None:
            service.tax_rate = body.tax_rate
        if body.erfolgsneutral is not None:
            service.erfolgsneutral = body.erfolgsneutral
            refresh_group_assignment = True
        service.valid_from = body.valid_from
        service.valid_to = body.valid_to
        if body.service_type_manual is not None:
            service.service_type_manual = body.service_type_manual
        if body.tax_rate_manual is not None:
            service.tax_rate_manual = body.tax_rate_manual
        service.updated_at = _utcnow()
        self._session.add(service)
        if refresh_group_assignment:
            await self.ensure_default_groups(mandant_id)
            await self._session.flush()
            await self.ensure_service_group_assignment(mandant_id, service)
        await self._session.commit()
        await self._session.refresh(service)
        await self.detect_service_type_for_service(mandant_id, service.id)
        await self._trigger_revalidation(service.partner_id)
        return await self._to_response(service)

    async def delete_service(self, service_id: UUID, mandant_id: UUID) -> None:
        service = await self._get_service(service_id, mandant_id)
        if service.is_base_service:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Base service cannot be deleted")
        partner_id = service.partner_id
        await self._session.delete(service)
        await self._session.commit()
        await self._trigger_revalidation(partner_id)

    async def create_matcher(self, service_id: UUID, mandant_id: UUID, body: CreateServiceMatcherRequest):
        service = await self._get_service(service_id, mandant_id)
        self._ensure_matcher_allowed(service)
        self._validate_pattern(body.pattern, body.pattern_type)
        await self._ensure_unique_matcher(service_id, body.pattern, body.pattern_type)
        now = _utcnow()
        matcher = ServiceMatcher(
            service_id=service_id,
            pattern=body.pattern,
            pattern_type=body.pattern_type.value,
            internal_only=body.internal_only,
            created_at=now,
            updated_at=now,
        )
        self._session.add(matcher)
        await self._session.commit()
        await self._session.refresh(matcher)
        await self._trigger_revalidation(service.partner_id)
        await self._recheck_new_partner_reviews(mandant_id, service.partner_id)
        return matcher

    async def update_matcher(
        self,
        service_id: UUID,
        matcher_id: UUID,
        mandant_id: UUID,
        body: UpdateServiceMatcherRequest,
    ):
        service = await self._get_service(service_id, mandant_id)
        self._ensure_matcher_allowed(service)
        matcher = await self._session.get(ServiceMatcher, matcher_id)
        if matcher is None or matcher.service_id != service_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service matcher not found")
        new_pattern = body.pattern if body.pattern is not None else matcher.pattern
        new_pattern_type = body.pattern_type if body.pattern_type is not None else ServiceMatcherType(matcher.pattern_type)
        self._validate_pattern(new_pattern, new_pattern_type)
        if new_pattern != matcher.pattern or new_pattern_type.value != matcher.pattern_type:
            await self._ensure_unique_matcher(service_id, new_pattern, new_pattern_type, exclude_matcher_id=matcher.id)
        matcher.pattern = new_pattern
        matcher.pattern_type = new_pattern_type.value
        if body.internal_only is not None:
            matcher.internal_only = body.internal_only
        matcher.updated_at = _utcnow()
        self._session.add(matcher)
        await self._session.commit()
        await self._session.refresh(matcher)
        await self._trigger_revalidation(service.partner_id)
        await self._recheck_new_partner_reviews(mandant_id, service.partner_id)
        return matcher

    async def delete_matcher(self, service_id: UUID, matcher_id: UUID, mandant_id: UUID) -> None:
        service = await self._get_service(service_id, mandant_id)
        self._ensure_matcher_allowed(service)
        matcher = await self._session.get(ServiceMatcher, matcher_id)
        if matcher is None or matcher.service_id != service_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service matcher not found")
        await self._session.delete(matcher)
        await self._session.commit()
        await self._trigger_revalidation(service.partner_id)

    async def preview_matcher(
        self,
        service_id: UUID,
        mandant_id: UUID,
        body: CreateServiceMatcherRequest,
    ) -> MatcherPreviewResponse:
        """Gibt eine Vorschau zurück, welche Buchungszeilen ein noch nicht gespeicherter
        Matcher treffen würde – ohne Änderungen vorzunehmen."""
        #breakpoint()  # Debug breakpoint for "Matcher testen" backend flow
        service = await self._get_service(service_id, mandant_id)
        self._ensure_matcher_allowed(service)
        self._validate_pattern(body.pattern, body.pattern_type)

        mock_matcher = ServiceMatcher(
            service_id=service_id,
            pattern=body.pattern,
            pattern_type=body.pattern_type.value,
            internal_only=body.internal_only,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )

        # Buchungszeilen laden, die noch NICHT zu dieser Leistung gehören
        # (eigene Zeilen anderer Leistungen + Zeilen anderer Partner)
        # Achtung: UUID-Vergleich gegen service_id ist unzuverlässig (Hex vs Bindestriche),
        # daher Filterung im Python-Loop.
        lines = (
            await self._session.exec(
                select(JournalLine)
                .join(Partner, JournalLine.partner_id == Partner.id)
                .where(
                    Partner.mandant_id == mandant_id,
                )
            )
        ).all()

        matched_lines: list[MatcherPreviewLineItem] = []
        partner_name_cache: dict[UUID, str | None] = {}
        service_name_cache: dict[UUID, str | None] = {}
        partner_conflict_cache: dict[UUID, PartnerAssignmentCriteria] = {}
        service_id_hex = service_id.hex.lower()

        for line in lines:
            # Zeilen, die bereits zu dieser Leistung gehören, überspringen
            line_service_uuid: UUID | None = None
            if line.service_id is not None:
                try:
                    line_service_uuid = UUID(str(line.service_id))
                except (ValueError, TypeError):
                    line_service_uuid = None
            # Name der aktuell zugeordneten Leistung für die Vorschau auflösen.
            line_service_name: str | None = None
            if line_service_uuid is not None:
                if line_service_uuid not in service_name_cache:
                    current_service = await self._session.get(Service, line_service_uuid)
                    service_name_cache[line_service_uuid] = current_service.name if current_service is not None else None
                line_service_name = service_name_cache[line_service_uuid]
            #if "Microsoft" == line_service_name:
            #    pass
            if line_service_uuid == service_id:
                continue
            if line.service_id is not None:
                # Fallback für inkonsistente UUID-String-Repräsentationen
                # (z. B. mit/ohne Bindestriche oder mit Prefix).
                line_service_hex = re.sub(r"[^0-9a-fA-F]", "", str(line.service_id)).lower()
                if len(line_service_hex) == 32 and line_service_hex == service_id_hex:
                    continue
            if not self._service_matches_line(service, [mock_matcher], line):
                continue
            if line.partner_id not in partner_name_cache:
                p = await self._session.get(Partner, line.partner_id)
                partner_name_cache[line.partner_id] = (
                    (p.display_name or p.name) if p else None
                )
            conflict_reasons: list[str] = []
            if line.partner_id is not None and line.partner_id != service.partner_id:
                if line.partner_id not in partner_conflict_cache:
                    partner_conflict_cache[line.partner_id] = await load_partner_assignment_criteria(self._session, line.partner_id)
                conflict_reasons = detect_conflicting_criteria(partner_conflict_cache[line.partner_id], line)
            matched_lines.append(
                MatcherPreviewLineItem(
                    journal_line_id=line.id,
                    partner_name_raw=line.partner_name_raw,
                    current_partner_name=partner_name_cache.get(line.partner_id),
                    current_service_name=line_service_name,
                    has_conflicting_partner_criteria=bool(conflict_reasons),
                    conflicting_partner_criteria=conflict_reasons,
                    booking_date=line.booking_date,
                    valuta_date=line.valuta_date,
                    amount=Decimal(str(line.amount)),
                    currency=line.currency,
                    text=line.text,
                )
            )

        matched_lines.sort(key=lambda x: x.booking_date, reverse=True)
        matched_lines.sort(key=lambda x: not x.has_conflicting_partner_criteria)
        return MatcherPreviewResponse(matched_lines=matched_lines, total=len(matched_lines))

    async def list_keywords(self, mandant_id: UUID) -> ServiceTypeKeywordListResponse:
        items = (
            await self._session.exec(
                select(ServiceTypeKeyword).where(ServiceTypeKeyword.mandant_id == mandant_id).order_by(ServiceTypeKeyword.target_service_type, ServiceTypeKeyword.pattern)
            )
        ).all()
        return ServiceTypeKeywordListResponse(
            items=[ServiceTypeKeywordResponse.model_validate(item) for item in items],
            system_defaults=list(SYSTEM_DEFAULT_KEYWORDS),
        )

    async def create_keyword(self, mandant_id: UUID, body: CreateServiceTypeKeywordRequest) -> ServiceTypeKeywordResponse:
        self._validate_pattern(body.pattern, body.pattern_type)
        await self._ensure_unique_keyword(mandant_id, body.pattern, body.pattern_type, body.target_service_type)
        now = _utcnow()
        entity = ServiceTypeKeyword(
            mandant_id=mandant_id,
            pattern=body.pattern,
            pattern_type=body.pattern_type.value,
            target_service_type=body.target_service_type.value,
            created_at=now,
            updated_at=now,
        )
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return ServiceTypeKeywordResponse.model_validate(entity)

    async def list_service_groups(
        self,
        mandant_id: UUID,
        section: ServiceGroupSection,
    ) -> list[ServiceGroupResponse]:
        await self.ensure_default_groups(mandant_id)
        groups = (
            await self._session.exec(
                select(ServiceGroup)
                .where(ServiceGroup.mandant_id == mandant_id, ServiceGroup.section == section.value)
                .order_by(ServiceGroup.sort_order, ServiceGroup.name)
            )
        ).all()
        return [ServiceGroupResponse.model_validate(group) for group in groups]

    async def create_service_group(self, mandant_id: UUID, body: CreateServiceGroupRequest) -> ServiceGroupResponse:
        await self.ensure_default_groups(mandant_id)
        await self._ensure_unique_group_name(mandant_id, body.section, body.name)
        group = ServiceGroup(
            mandant_id=mandant_id,
            section=body.section.value,
            name=body.name.strip(),
            sort_order=body.sort_order,
            is_default=False,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return ServiceGroupResponse.model_validate(group)

    async def update_service_group(
        self,
        mandant_id: UUID,
        group_id: UUID,
        body: UpdateServiceGroupRequest,
    ) -> ServiceGroupResponse:
        group = await self._get_service_group(mandant_id, group_id)
        if body.name is not None:
            await self._ensure_unique_group_name(
                mandant_id,
                ServiceGroupSection(group.section),
                body.name,
                exclude_group_id=group.id,
            )
            group.name = body.name.strip()
        if body.sort_order is not None:
            group.sort_order = body.sort_order
        group.updated_at = _utcnow()
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return ServiceGroupResponse.model_validate(group)

    async def delete_service_group(
        self,
        mandant_id: UUID,
        group_id: UUID,
        body: DeleteServiceGroupRequest,
    ) -> None:
        group = await self._get_service_group(mandant_id, group_id)
        assignments = (
            await self._session.exec(
                select(ServiceGroupAssignment).where(
                    ServiceGroupAssignment.mandant_id == mandant_id,
                    ServiceGroupAssignment.service_group_id == group.id,
                )
            )
        ).all()
        if assignments and body.reassign_to_group_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Group has assigned services. Provide reassign_to_group_id.",
            )
        if assignments and body.reassign_to_group_id is not None:
            target_group = await self._get_service_group(mandant_id, body.reassign_to_group_id)
            if target_group.section != group.section:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Reassignment target must be in the same section.",
                )
            for assignment in assignments:
                assignment.service_group_id = target_group.id
                assignment.updated_at = _utcnow()
                self._session.add(assignment)
        if assignments and body.reassign_to_group_id == group.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Cannot reassign to the same group.",
            )

        await self._session.delete(group)
        await self._session.commit()

    async def assign_service_group(
        self,
        mandant_id: UUID,
        service_id: UUID,
        service_group_id: UUID,
    ) -> ServiceGroupAssignmentResponse:
        await self.ensure_default_groups(mandant_id)
        service = await self._get_service(service_id, mandant_id)
        target_group = await self._get_service_group(mandant_id, service_group_id)
        service_section = self._determine_service_section(service)
        if service_section is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Service is not eligible for income-expense grouping.",
            )
        if target_group.section != service_section.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Cross-section assignments are not allowed.",
            )

        assignment = (
            await self._session.exec(
                select(ServiceGroupAssignment).where(
                    ServiceGroupAssignment.mandant_id == mandant_id,
                    ServiceGroupAssignment.service_id == service.id,
                )
            )
        ).first()
        if assignment is None:
            assignment = ServiceGroupAssignment(
                mandant_id=mandant_id,
                service_id=service.id,
                service_group_id=target_group.id,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        else:
            assignment.service_group_id = target_group.id
            assignment.updated_at = _utcnow()
        self._session.add(assignment)
        await self._session.commit()
        await self._session.refresh(assignment)
        return ServiceGroupAssignmentResponse.model_validate(assignment)

    async def ensure_default_groups(self, mandant_id: UUID) -> None:
        existing = (
            await self._session.exec(
                select(ServiceGroup).where(ServiceGroup.mandant_id == mandant_id)
            )
        ).all()
        existing_by_section: dict[ServiceGroupSection, list[ServiceGroup]] = {
            ServiceGroupSection.income: [],
            ServiceGroupSection.expense: [],
            ServiceGroupSection.neutral: [],
        }
        for group in existing:
            existing_by_section[ServiceGroupSection(group.section)].append(group)

        changed = False
        for section, default_names in DEFAULT_GROUPS_BY_SECTION.items():
            if existing_by_section[section]:
                continue
            for sort_order, name in enumerate(default_names):
                self._session.add(
                    ServiceGroup(
                        mandant_id=mandant_id,
                        section=section.value,
                        name=name,
                        sort_order=sort_order,
                        is_default=True,
                        created_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                )
                changed = True
        if changed:
            await self._session.commit()

    async def list_groups_by_section(self, mandant_id: UUID) -> dict[ServiceGroupSection, list[ServiceGroup]]:
        groups = (
            await self._session.exec(
                select(ServiceGroup)
                .where(ServiceGroup.mandant_id == mandant_id)
                .order_by(ServiceGroup.section, ServiceGroup.sort_order, ServiceGroup.name)
            )
        ).all()
        groups_by_section: dict[ServiceGroupSection, list[ServiceGroup]] = {
            ServiceGroupSection.income: [],
            ServiceGroupSection.expense: [],
            ServiceGroupSection.neutral: [],
        }
        for group in groups:
            groups_by_section[ServiceGroupSection(group.section)].append(group)
        return groups_by_section

    def _preferred_default_group_name(self, service: Service) -> str | None:
        if service.erfolgsneutral:
            return "Erfolgsneutrale Zahlungen"
        return DEFAULT_GROUP_BY_SERVICE_TYPE.get(service.service_type)

    def _select_default_group(
        self,
        service: Service,
        groups_by_section: dict[ServiceGroupSection, list[ServiceGroup]],
    ) -> ServiceGroup | None:
        service_section = self._determine_service_section(service)
        if service_section is None:
            return None
        section_groups = groups_by_section[service_section]
        if not section_groups:
            return None
        preferred_name = self._preferred_default_group_name(service)
        if preferred_name is not None:
            preferred_group = next((group for group in section_groups if group.name == preferred_name), None)
            if preferred_group is not None:
                return preferred_group
        return section_groups[0]

    async def ensure_service_group_assignment(
        self,
        mandant_id: UUID,
        service: Service,
        groups_by_section: dict[ServiceGroupSection, list[ServiceGroup]] | None = None,
        assignment: ServiceGroupAssignment | None = None,
    ) -> ServiceGroupAssignment | None:
        service_section = self._determine_service_section(service)
        if service_section is None:
            return None
        if groups_by_section is None:
            groups_by_section = await self.list_groups_by_section(mandant_id)
        target_group = self._select_default_group(service, groups_by_section)
        if target_group is None:
            return None
        if assignment is None:
            assignment = (
                await self._session.exec(
                    select(ServiceGroupAssignment).where(
                        ServiceGroupAssignment.mandant_id == mandant_id,
                        ServiceGroupAssignment.service_id == service.id,
                    )
                )
            ).first()
        if assignment is None:
            assignment = ServiceGroupAssignment(
                mandant_id=mandant_id,
                service_id=service.id,
                service_group_id=target_group.id,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            self._session.add(assignment)
            return assignment
        current_group = next(
            (
                group
                for section_groups in groups_by_section.values()
                for group in section_groups
                if group.id == assignment.service_group_id
            ),
            None,
        )
        if current_group is None:
            current_group = await self._session.get(ServiceGroup, assignment.service_group_id)
        if current_group is not None and not current_group.is_default:
            return assignment
        if current_group is not None and current_group.section == service_section.value:
            # Default-Gruppe in der richtigen Sektion: nur in die bevorzugte Gruppe verschieben,
            # wenn diese explizit existiert. Gibt es keinen passenden Gruppennamen, bleibt die
            # Zuweisung erhalten (verhindert Zurücksetzen auf section_groups[0]).
            preferred_name = self._preferred_default_group_name(service)
            if preferred_name is not None:
                preferred_group = next(
                    (g for g in groups_by_section[service_section] if g.name == preferred_name),
                    None,
                )
                if preferred_group is not None and assignment.service_group_id != preferred_group.id:
                    assignment.service_group_id = preferred_group.id
                    assignment.updated_at = _utcnow()
                    self._session.add(assignment)
            return assignment
        if assignment.service_group_id != target_group.id:
            assignment.service_group_id = target_group.id
            assignment.updated_at = _utcnow()
            self._session.add(assignment)
        return assignment

    async def update_keyword(
        self,
        mandant_id: UUID,
        keyword_id: UUID,
        body: UpdateServiceTypeKeywordRequest,
    ) -> ServiceTypeKeywordResponse:
        entity = await self._session.get(ServiceTypeKeyword, keyword_id)
        if entity is None or entity.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service keyword not found")
        new_pattern = body.pattern if body.pattern is not None else entity.pattern
        new_pattern_type = body.pattern_type if body.pattern_type is not None else ServiceMatcherType(entity.pattern_type)
        new_target = body.target_service_type if body.target_service_type is not None else KeywordTargetType(entity.target_service_type)
        self._validate_pattern(new_pattern, new_pattern_type)
        if new_pattern != entity.pattern or new_pattern_type.value != entity.pattern_type or new_target.value != entity.target_service_type:
            await self._ensure_unique_keyword(mandant_id, new_pattern, new_pattern_type, new_target, exclude_keyword_id=entity.id)
        entity.pattern = new_pattern
        entity.pattern_type = new_pattern_type.value
        entity.target_service_type = new_target.value
        entity.updated_at = _utcnow()
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return ServiceTypeKeywordResponse.model_validate(entity)

    async def delete_keyword(self, mandant_id: UUID, keyword_id: UUID) -> None:
        entity = await self._session.get(ServiceTypeKeyword, keyword_id)
        if entity is None or entity.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service keyword not found")
        await self._session.delete(entity)
        await self._session.commit()

    async def auto_assign_journal_line(self, mandant_id: UUID, line: JournalLine) -> None:
        if line.partner_id is None:
            line.service_id = None
            line.service_assignment_mode = None
            self._session.add(line)
            return

        services, matchers_by_service = await self._load_partner_services(line.partner_id)
        assignment = await self._calculate_assignment(line, services, matchers_by_service)
        line.service_id = assignment.service_id
        line.service_assignment_mode = "auto"
        self._session.add(line)

        if assignment.reason == "multiple_matches":
            await self._upsert_service_assignment_review(
                mandant_id=mandant_id,
                journal_line_id=line.id,
                current_service_id=line.service_id,
                proposed_service_id=None,
                reason=assignment.reason,
                matching_service_ids=assignment.matching_service_ids,
            )
        else:
            await self._clear_service_assignment_review(line.id)

        # Trigger manual-assignment review if partner requires it and line lands on base service
        if assignment.reason in ("no_match_base_service", "multiple_matches"):
            partner = await self._session.get(Partner, line.partner_id)
            if partner is not None and partner.manual_assignment:
                await self._upsert_manual_service_assignment_review(mandant_id, line.id)
            else:
                await self._clear_manual_service_assignment_review(line.id)
        else:
            await self._clear_manual_service_assignment_review(line.id)

        await self.detect_service_type_for_service(mandant_id, line.service_id)

    async def manually_assign_journal_line(
        self,
        mandant_id: UUID,
        line: JournalLine,
        service_id: UUID,
    ) -> None:
        if line.partner_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Journal line has no partner")

        service = await self._get_service(service_id, mandant_id)
        if service.partner_id != line.partner_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Service does not belong to journal line partner")
        if not self._is_service_valid_for_booking_date(service, line.booking_date):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Service is not valid for journal line booking_date")

        line.service_id = service.id
        line.service_assignment_mode = "manual"
        self._session.add(line)
        await self._clear_service_assignment_review(line.id)
        await self._clear_manual_service_assignment_review(line.id)
        await self.detect_service_type_for_service(mandant_id, service.id)

    async def revalidate_partner_lines(self, partner_id: UUID) -> None:
        partner = await self._session.get(Partner, partner_id)
        if partner is None:
            return

        services, matchers_by_service = await self._load_partner_services(partner_id)
        lines = (
            await self._session.exec(
                select(JournalLine).where(JournalLine.partner_id == partner_id).order_by(JournalLine.created_at)
            )
        ).all()
        touched_service_ids: set[UUID] = set()

        for line in lines:
            if line.service_id is not None:
                touched_service_ids.add(line.service_id)

            assignment = await self._calculate_assignment(line, services, matchers_by_service)
            touched_service_ids.add(assignment.service_id)

            if assignment.reason == "multiple_matches":
                await self._upsert_service_assignment_review(
                    mandant_id=partner.mandant_id,
                    journal_line_id=line.id,
                    current_service_id=line.service_id,
                    proposed_service_id=None,
                    reason=assignment.reason,
                    matching_service_ids=assignment.matching_service_ids,
                )
                if partner.manual_assignment:
                    await self._upsert_manual_service_assignment_review(partner.mandant_id, line.id)
                else:
                    await self._clear_manual_service_assignment_review(line.id)
                continue

            if line.service_id == assignment.service_id:
                await self._clear_service_assignment_review(line.id)
                if assignment.reason == "no_match_base_service" and partner.manual_assignment:
                    await self._upsert_manual_service_assignment_review(partner.mandant_id, line.id)
                else:
                    await self._clear_manual_service_assignment_review(line.id)
                continue

            line.service_id = assignment.service_id
            line.service_assignment_mode = "auto"
            self._session.add(line)
            await self._clear_service_assignment_review(line.id)
            if assignment.reason == "no_match_base_service" and partner.manual_assignment:
                await self._upsert_manual_service_assignment_review(partner.mandant_id, line.id)
            else:
                await self._clear_manual_service_assignment_review(line.id)

        for service_id in touched_service_ids:
            await self.detect_service_type_for_service(partner.mandant_id, service_id)

        await self._session.commit()

    async def detect_service_type_for_service(self, mandant_id: UUID, service_id: UUID | None) -> None:
        if service_id is None:
            return

        service = await self._get_service(service_id, mandant_id)
        existing_review = await self._get_service_type_review(service.id)
        if service.service_type_manual:
            return
        if service.service_type != ServiceType.unknown.value and existing_review is None:
            return

        lines = (
            await self._session.exec(
                select(JournalLine).where(JournalLine.service_id == service.id).order_by(JournalLine.created_at)
            )
        ).all()
        if not lines:
            await self._clear_service_type_review(service.id)
            return

        rules = await self._load_keyword_rules(mandant_id)
        votes: Counter[ServiceType] = Counter()
        reasons: list[str] = []
        for line in lines:
            detected_type, reason = self._detect_type_for_line(line, rules)
            votes[detected_type] += 1
            reasons.append(reason)

        detected_service_type, _ = votes.most_common(1)[0]
        previous_type = service.service_type
        if previous_type != detected_service_type.value:
            service.service_type = detected_service_type.value
            if not service.tax_rate_manual:
                service.tax_rate = _default_tax_rate(detected_service_type)
            service.updated_at = _utcnow()
            self._session.add(service)

        if previous_type == detected_service_type.value and existing_review is None:
            return

        review_previous_type = previous_type
        if existing_review is not None:
            review_previous_type = existing_review.context.get("previous_type", previous_type)

        await self._upsert_service_type_review(
            mandant_id=mandant_id,
            service_id=service.id,
            previous_type=review_previous_type,
            auto_assigned_type=detected_service_type.value,
            auto_assigned_tax_rate=str(_default_tax_rate(detected_service_type)),
            reason=reasons[0],
            current_journal_line_ids=[str(line.id) for line in lines],
        )

    async def _get_partner(self, partner_id: UUID, mandant_id: UUID) -> Partner:
        partner = await self._session.get(Partner, partner_id)
        if partner is None or partner.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
        return partner

    async def _get_service(self, service_id: UUID, mandant_id: UUID) -> Service:
        service = await self._session.get(Service, service_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        await self._get_partner(service.partner_id, mandant_id)
        return service

    async def _get_service_group(self, mandant_id: UUID, group_id: UUID) -> ServiceGroup:
        group = await self._session.get(ServiceGroup, group_id)
        if group is None or group.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service group not found")
        return group

    async def _ensure_unique_group_name(
        self,
        mandant_id: UUID,
        section: ServiceGroupSection,
        name: str,
        exclude_group_id: UUID | None = None,
    ) -> None:
        normalized_name = name.strip()
        existing = (
            await self._session.exec(
                select(ServiceGroup).where(
                    ServiceGroup.mandant_id == mandant_id,
                    ServiceGroup.section == section.value,
                    ServiceGroup.name == normalized_name,
                )
            )
        ).first()
        if existing is not None and existing.id != exclude_group_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service group with this name already exists")

    def _determine_service_section(self, service: Service) -> ServiceGroupSection | None:
        if service.erfolgsneutral:
            return ServiceGroupSection.neutral
        if service.service_type == ServiceType.customer.value:
            return ServiceGroupSection.income
        if service.service_type in _EXPENSE_SERVICE_TYPES:
            return ServiceGroupSection.expense
        return None

    async def _load_partner_services(
        self,
        partner_id: UUID,
    ) -> tuple[list[Service], dict[UUID, list[ServiceMatcher]]]:
        services = (
            await self._session.exec(
                select(Service).where(Service.partner_id == partner_id).order_by(desc(Service.is_base_service), Service.name)
            )
        ).all()
        base_service = next((service for service in services if service.is_base_service), None)
        if base_service is None:
            base_service = await ensure_base_service(self._session, partner_id)
            services = [base_service, *services]

        matchers = (
            await self._session.exec(
                select(ServiceMatcher)
                .join(Service, Service.id == ServiceMatcher.service_id)
                .where(Service.partner_id == partner_id)
                .order_by(ServiceMatcher.created_at)
            )
        ).all()
        matchers_by_service: dict[UUID, list[ServiceMatcher]] = {}
        for matcher in matchers:
            matchers_by_service.setdefault(matcher.service_id, []).append(matcher)
        return services, matchers_by_service

    async def _calculate_assignment(
        self,
        line: JournalLine,
        services: list[Service],
        matchers_by_service: dict[UUID, list[ServiceMatcher]],
    ) -> ServiceAssignmentResult:
        if line.partner_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Journal line has no partner")

        base_service = next((service for service in services if service.is_base_service), None)
        if base_service is None:
            base_service = await ensure_base_service(self._session, line.partner_id)

        matching_service_ids: list[UUID] = []
        for service in services:
            if service.is_base_service:
                continue
            if not self._is_service_valid_for_booking_date(service, line.booking_date):
                continue
            if self._service_matches_line(service, matchers_by_service.get(service.id, []), line):
                matching_service_ids.append(service.id)

        if len(matching_service_ids) == 1:
            return ServiceAssignmentResult(
                service_id=matching_service_ids[0],
                matching_service_ids=matching_service_ids,
                reason="single_match",
            )
        if len(matching_service_ids) > 1:
            return ServiceAssignmentResult(
                service_id=base_service.id,
                matching_service_ids=matching_service_ids,
                reason="multiple_matches",
            )
        return ServiceAssignmentResult(
            service_id=base_service.id,
            matching_service_ids=[],
            reason="no_match_base_service",
        )

    async def _to_response(self, service: Service) -> ServiceResponse:
        matchers = (
            await self._session.exec(
                select(ServiceMatcher).where(ServiceMatcher.service_id == service.id).order_by(ServiceMatcher.created_at)
            )
        ).all()
        journal_line_count = (
            await self._session.exec(
                select(func.count()).select_from(JournalLine).where(JournalLine.service_id == service.id)
            )
        ).one()
        return ServiceResponse(
            id=service.id,
            partner_id=service.partner_id,
            name=service.name,
            description=service.description,
            service_type=ServiceType(service.service_type),
            tax_rate=service.tax_rate,
            erfolgsneutral=service.erfolgsneutral,
            valid_from=service.valid_from,
            valid_to=service.valid_to,
            is_base_service=service.is_base_service,
            service_type_manual=service.service_type_manual,
            tax_rate_manual=service.tax_rate_manual,
            created_at=service.created_at,
            updated_at=service.updated_at,
            journal_line_count=journal_line_count,
            matchers=[
                {
                    "id": matcher.id,
                    "pattern": matcher.pattern,
                    "pattern_type": ServiceMatcherType(matcher.pattern_type),
                    "internal_only": matcher.internal_only,
                    "created_at": matcher.created_at,
                    "updated_at": matcher.updated_at,
                }
                for matcher in matchers
            ],
        )

    async def _ensure_unique_service_name(self, partner_id: UUID, name: str, exclude_service_id: UUID | None = None) -> None:
        existing = (await self._session.exec(select(Service).where(Service.partner_id == partner_id, Service.name == name))).first()
        if existing is not None and existing.id != exclude_service_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service with this name already exists for partner")

    async def _ensure_unique_matcher(
        self,
        service_id: UUID,
        pattern: str,
        pattern_type: ServiceMatcherType,
        exclude_matcher_id: UUID | None = None,
    ) -> None:
        existing = (
            await self._session.exec(
                select(ServiceMatcher).where(
                    ServiceMatcher.service_id == service_id,
                    ServiceMatcher.pattern == pattern,
                    ServiceMatcher.pattern_type == pattern_type.value,
                )
            )
        ).first()
        if existing is not None and existing.id != exclude_matcher_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service matcher already exists")

    async def _ensure_unique_keyword(
        self,
        mandant_id: UUID,
        pattern: str,
        pattern_type: ServiceMatcherType,
        target_service_type: KeywordTargetType,
        exclude_keyword_id: UUID | None = None,
    ) -> None:
        existing = (
            await self._session.exec(
                select(ServiceTypeKeyword).where(
                    ServiceTypeKeyword.mandant_id == mandant_id,
                    ServiceTypeKeyword.pattern == pattern,
                    ServiceTypeKeyword.pattern_type == pattern_type.value,
                    ServiceTypeKeyword.target_service_type == target_service_type.value,
                )
            )
        ).first()
        if existing is not None and existing.id != exclude_keyword_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service keyword rule already exists")

    def _validate_pattern(self, pattern: str, pattern_type: ServiceMatcherType) -> None:
        if pattern_type != ServiceMatcherType.regex:
            return
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Invalid regex pattern: {exc}") from exc

    def _ensure_matcher_allowed(self, service: Service) -> None:
        if service.is_base_service:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Base service cannot have matchers")

    async def _trigger_revalidation(self, partner_id: UUID) -> None:
        await self.revalidate_partner_lines(partner_id)

    async def _recheck_new_partner_reviews(self, mandant_id: UUID, changed_partner_id: UUID) -> None:
        """Prüft nach einer Matcher-Änderung alle anderen Partner des Mandanten.

        Dieselbe Logik wie die Preview: lädt alle Buchungszeilen anderer Partner,
        prüft ob ein Matcher des geänderten Partners trifft. Nur die treffenden
        Zeilen werden umgezogen. Der Quell-Partner wird gelöscht sofern er danach
        keine Zeilen mehr hat.
        """
        services, matchers_by_service = await self._load_partner_services(changed_partner_id)
        has_matchers = any(
            not svc.is_base_service and bool(matchers_by_service.get(svc.id))
            for svc in services
        )
        if not has_matchers:
            await self._session.commit()
            return

        # Alle Buchungszeilen anderer Partner desselben Mandanten laden
        other_lines = (
            await self._session.exec(
                select(JournalLine)
                .join(Partner, JournalLine.partner_id == Partner.id)
                .where(
                    Partner.mandant_id == mandant_id,
                    JournalLine.partner_id != changed_partner_id,
                )
            )
        ).all()

        # Treffende Zeilen nach partner_id gruppieren
        matching_by_partner: dict[UUID, list[JournalLine]] = {}
        for line in other_lines:
            if line.partner_id is None:
                continue
            matched = any(
                not service.is_base_service
                and bool(matchers_by_service.get(service.id))
                and self._service_matches_line(service, matchers_by_service.get(service.id, []), line)
                for service in services
            )
            if matched:
                matching_by_partner.setdefault(line.partner_id, []).append(line)

        if not matching_by_partner:
            await self._session.commit()
            return

        needs_revalidation = False

        for other_partner_id, matched_lines in matching_by_partner.items():
            # Nur die treffenden Zeilen verschieben (nicht alle des Partners)
            await self.prepare_lines_for_partner_change(mandant_id, list(matched_lines), changed_partner_id)
            needs_revalidation = True

            # Partner löschen falls danach keine Zeilen mehr übrig
            remaining = (
                await self._session.exec(
                    select(JournalLine).where(JournalLine.partner_id == other_partner_id)
                )
            ).all()
            if not remaining:
                other_partner = await self._session.get(Partner, other_partner_id)
                if other_partner is not None and other_partner.mandant_id == mandant_id:
                    await delete_partner_clean(
                        self._session,
                        other_partner,
                        detach_journal_lines=False,
                    )

        if needs_revalidation:
            await self.revalidate_partner_lines(changed_partner_id)
        else:
            await self._session.commit()

    def _is_service_valid_for_booking_date(self, service: Service, booking_date_raw: str) -> bool:
        booking_date = date.fromisoformat(booking_date_raw)
        if service.valid_from is not None and booking_date < service.valid_from:
            return False
        if service.valid_to is not None and booking_date > service.valid_to:
            return False
        return True

    def _service_matches_line(self, _service: Service, matchers: list[ServiceMatcher], line: JournalLine) -> bool:
        searchable_text = "\n".join(filter(None, [line.text or "", line.partner_name_raw or ""]))
        searchable_text_lower = searchable_text.lower()
        for matcher in matchers:
            if matcher.internal_only and line.partner_id != _service.partner_id:
                continue
            if matcher.pattern_type == ServiceMatcherType.string.value:
                if matcher.pattern.lower() in searchable_text_lower:
                    return True
                continue
            if re.search(matcher.pattern, searchable_text, re.IGNORECASE):
                return True
        return False

    async def _get_service_assignment_review(self, journal_line_id: UUID) -> ReviewItem | None:
        return (
            await self._session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_assignment",
                    ReviewItem.journal_line_id == journal_line_id,
                )
            )
        ).first()

    async def _get_service_type_review(self, service_id: UUID) -> ReviewItem | None:
        return (
            await self._session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_type_review",
                    ReviewItem.service_id == service_id,
                )
            )
        ).first()

    async def _upsert_service_assignment_review(
        self,
        mandant_id: UUID,
        journal_line_id: UUID,
        current_service_id: UUID | None,
        proposed_service_id: UUID | None,
        reason: str,
        matching_service_ids: list[UUID] | None = None,
    ) -> None:
        review = await self._get_service_assignment_review(journal_line_id)
        context = {
            "current_service_id": str(current_service_id) if current_service_id else None,
            "proposed_service_id": str(proposed_service_id) if proposed_service_id else None,
            "reason": reason,
        }
        if matching_service_ids is not None:
            context["matching_services"] = [str(service_id) for service_id in matching_service_ids]

        if review is None:
            review = ReviewItem(
                mandant_id=mandant_id,
                item_type="service_assignment",
                journal_line_id=journal_line_id,
                context=context,
                status="open",
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        else:
            review.context = context
            review.status = "open"
            review.updated_at = _utcnow()
            review.resolved_by = None
            review.resolved_at = None
        self._session.add(review)

    async def _upsert_service_type_review(
        self,
        mandant_id: UUID,
        service_id: UUID,
        previous_type: str,
        auto_assigned_type: str,
        auto_assigned_tax_rate: str,
        reason: str,
        current_journal_line_ids: list[str],
    ) -> None:
        review = await self._get_service_type_review(service_id)
        context = {
            "previous_type": previous_type,
            "auto_assigned_type": auto_assigned_type,
            "auto_assigned_tax_rate": auto_assigned_tax_rate,
            "reason": reason,
            "current_journal_line_ids": current_journal_line_ids,
        }

        if review is None:
            review = ReviewItem(
                mandant_id=mandant_id,
                item_type="service_type_review",
                service_id=service_id,
                context=context,
                status="open",
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        else:
            review.context = context
            review.status = "open"
            review.updated_at = _utcnow()
            review.resolved_by = None
            review.resolved_at = None
        self._session.add(review)

    async def create_manual_assignment_reviews_for_partner(
        self, partner_id: UUID, mandant_id: UUID
    ) -> None:
        """Creates manual_service_assignment review items for all journal lines
        currently on the base service of the given partner."""
        base_service = (
            await self._session.exec(
                select(Service).where(Service.partner_id == partner_id, Service.is_base_service == True)  # noqa: E712
            )
        ).first()
        if base_service is None:
            return
        lines = (
            await self._session.exec(
                select(JournalLine).where(JournalLine.service_id == base_service.id)
            )
        ).all()
        for line in lines:
            await self._upsert_manual_service_assignment_review(mandant_id, line.id)
        if lines:
            await self._session.flush()

    async def delete_manual_assignment_reviews_for_partner(self, partner_id: UUID) -> None:
        """Deletes all open manual_service_assignment review items for a partner's lines."""
        reviews = (
            await self._session.exec(
                select(ReviewItem)
                .join(JournalLine, ReviewItem.journal_line_id == JournalLine.id)
                .where(
                    ReviewItem.item_type == "manual_service_assignment",
                    ReviewItem.status == "open",
                    JournalLine.partner_id == partner_id,
                )
            )
        ).all()
        for review in reviews:
            await self._session.delete(review)

    async def _get_manual_service_assignment_review(self, journal_line_id: UUID) -> ReviewItem | None:
        return (
            await self._session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "manual_service_assignment",
                    ReviewItem.journal_line_id == journal_line_id,
                    ReviewItem.status == "open",
                )
            )
        ).first()

    async def _upsert_manual_service_assignment_review(
        self,
        mandant_id: UUID,
        journal_line_id: UUID,
    ) -> None:
        review = await self._get_manual_service_assignment_review(journal_line_id)
        if review is not None:
            return  # already open, no action needed
        review = ReviewItem(
            mandant_id=mandant_id,
            item_type="manual_service_assignment",
            journal_line_id=journal_line_id,
            context={},
            status="open",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self._session.add(review)

    async def _clear_manual_service_assignment_review(self, journal_line_id: UUID | None) -> None:
        if journal_line_id is None:
            return
        review = await self._get_manual_service_assignment_review(journal_line_id)
        if review is None:
            return
        await self._session.delete(review)

    async def _clear_service_assignment_review(self, journal_line_id: UUID | None) -> None:
        if journal_line_id is None:
            return
        review = await self._get_service_assignment_review(journal_line_id)
        if review is None or review.status != "open":
            return
        await self._session.delete(review)

    async def _clear_service_type_review(self, service_id: UUID | None) -> None:
        if service_id is None:
            return
        review = await self._get_service_type_review(service_id)
        if review is None or review.status != "open":
            return
        await self._session.delete(review)

    async def _delete_open_line_reviews(self, journal_line_ids: list[UUID]) -> None:
        if not journal_line_ids:
            return
        line_filters = [ReviewItem.journal_line_id == journal_line_id for journal_line_id in journal_line_ids]
        reviews = (
            await self._session.exec(
                select(ReviewItem).where(
                    ReviewItem.status == "open",
                    or_(*line_filters),
                )
            )
        ).all()
        for review in reviews:
            await self._session.delete(review)

    async def _load_keyword_rules(self, mandant_id: UUID) -> list[ServiceTypeKeyword | SystemServiceTypeKeywordResponse]:
        custom_rules = (
            await self._session.exec(
                select(ServiceTypeKeyword).where(ServiceTypeKeyword.mandant_id == mandant_id).order_by(ServiceTypeKeyword.created_at)
            )
        ).all()
        if custom_rules:
            return list(custom_rules)
        return list(SYSTEM_DEFAULT_KEYWORDS)

    def _detect_type_for_line(
        self,
        line: JournalLine,
        rules: list[ServiceTypeKeyword | SystemServiceTypeKeywordResponse],
    ) -> tuple[ServiceType, str]:
        searchable_text = line.text or ""
        for rule in rules:
            if self._pattern_matches(searchable_text, rule.pattern, rule.pattern_type):
                target_type = ServiceType(rule.target_service_type)
                return target_type, f"keyword:{rule.pattern}"
        if Decimal(str(line.amount)) <= Decimal("0.00"):
            return ServiceType.supplier, "amount<=0"
        return ServiceType.customer, "amount>0"

    def _pattern_matches(self, text: str, pattern: str, pattern_type: ServiceMatcherType | str) -> bool:
        pattern_kind = pattern_type.value if isinstance(pattern_type, ServiceMatcherType) else pattern_type
        if pattern_kind == ServiceMatcherType.string.value:
            return pattern.lower() in text.lower()
        return re.search(pattern, text, re.IGNORECASE) is not None
