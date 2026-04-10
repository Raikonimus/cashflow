from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_mandant_access, require_role
from app.auth.models import User
from app.core.database import get_session
from app.partners.models import MatchField, PartnerPatternType
from app.partners.schemas import (
    AddAccountRequest,
    AddIbanRequest,
    AddNameRequest,
    AddPatternRequest,
    CreatePartnerRequest,
    MergeRequest,
    MergeResponse,
    PaginatedAuditLogResponse,
    PaginatedPartnersResponse,
    PartnerAccountResponse,
    PartnerDetailResponse,
    PartnerIbanResponse,
    PartnerNameResponse,
    PartnerNeighbor,
    PartnerNeighborsResponse,
    PartnerPatternResponse,
    UpdatePartnerRequest,
)
from app.partners.service import AuditLogService, PartnerMergeService, PartnerService

partners_router = APIRouter(prefix="/mandants", tags=["partners"])


def _partner_svc(session: AsyncSession = Depends(get_session)) -> PartnerService:
    return PartnerService(session)


def _merge_svc(session: AsyncSession = Depends(get_session)) -> PartnerMergeService:
    return PartnerMergeService(session)


def _audit_svc(session: AsyncSession = Depends(get_session)) -> AuditLogService:
    return AuditLogService(session)


# ─── Partner CRUD ────────────────────────────────────────────────────────────

@partners_router.get("/{mandant_id}/partners", response_model=PaginatedPartnersResponse)
async def list_partners(
    mandant_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    include_inactive: bool = Query(default=False),
    search: str = Query(default=""),
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PaginatedPartnersResponse:
    return await svc.list_partners(mandant_id, page=page, size=size, include_inactive=include_inactive, search=search)


@partners_router.post(
    "/{mandant_id}/partners",
    response_model=PartnerDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_partner(
    mandant_id: UUID,
    body: CreatePartnerRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerDetailResponse:
    partner = await svc.create_partner(mandant_id, name=body.name, iban=body.iban)
    return await svc.get_partner_detail(partner.id, mandant_id)


@partners_router.get("/{mandant_id}/partners/{partner_id}", response_model=PartnerDetailResponse)
async def get_partner(
    mandant_id: UUID,
    partner_id: UUID,
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerDetailResponse:
    return await svc.get_partner_detail(partner_id, mandant_id)


@partners_router.patch("/{mandant_id}/partners/{partner_id}", response_model=PartnerDetailResponse)
async def update_partner(
    mandant_id: UUID,
    partner_id: UUID,
    body: UpdatePartnerRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerDetailResponse:
    return await svc.update_display_name(partner_id, mandant_id, body.display_name)


@partners_router.get("/{mandant_id}/partners/{partner_id}/neighbors", response_model=PartnerNeighborsResponse)
async def get_partner_neighbors(
    mandant_id: UUID,
    partner_id: UUID,
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerNeighborsResponse:
    return await svc.get_neighbors(partner_id, mandant_id)


# ─── IBAN endpoints ───────────────────────────────────────────────────────────

@partners_router.post(
    "/{mandant_id}/partners/{partner_id}/ibans",
    response_model=PartnerIbanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_iban(
    mandant_id: UUID,
    partner_id: UUID,
    body: AddIbanRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerIbanResponse:
    entity = await svc.add_iban(partner_id, mandant_id, body.iban)
    return PartnerIbanResponse.model_validate(entity)


@partners_router.delete(
    "/{mandant_id}/partners/{partner_id}/ibans/{iban_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_iban(
    mandant_id: UUID,
    partner_id: UUID,
    iban_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> None:
    await svc.remove_iban(iban_id, partner_id, mandant_id)


# ─── Account (BLZ + Kontonummer) endpoints ────────────────────────────────────

@partners_router.post(
    "/{mandant_id}/partners/{partner_id}/accounts",
    response_model=PartnerAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_account(
    mandant_id: UUID,
    partner_id: UUID,
    body: AddAccountRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerAccountResponse:
    entity = await svc.add_account(partner_id, mandant_id, body.account_number, body.blz, body.bic)
    return PartnerAccountResponse.model_validate(entity)


@partners_router.delete(
    "/{mandant_id}/partners/{partner_id}/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_account(
    mandant_id: UUID,
    partner_id: UUID,
    account_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> None:
    await svc.remove_account(account_id, partner_id, mandant_id)

@partners_router.post(
    "/{mandant_id}/partners/{partner_id}/names",
    response_model=PartnerNameResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_name(
    mandant_id: UUID,
    partner_id: UUID,
    body: AddNameRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerNameResponse:
    entity = await svc.add_name(partner_id, mandant_id, body.name)
    return PartnerNameResponse.model_validate(entity)


@partners_router.delete(
    "/{mandant_id}/partners/{partner_id}/names/{name_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_name(
    mandant_id: UUID,
    partner_id: UUID,
    name_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> None:
    await svc.remove_name(name_id, partner_id, mandant_id)


# ─── Pattern endpoints ────────────────────────────────────────────────────────

@partners_router.get(
    "/{mandant_id}/partners/{partner_id}/patterns",
    response_model=list[PartnerPatternResponse],
)
async def list_patterns(
    mandant_id: UUID,
    partner_id: UUID,
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> list[PartnerPatternResponse]:
    detail = await svc.get_partner_detail(partner_id, mandant_id)
    return detail.patterns


@partners_router.post(
    "/{mandant_id}/partners/{partner_id}/patterns",
    response_model=PartnerPatternResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_pattern(
    mandant_id: UUID,
    partner_id: UUID,
    body: AddPatternRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> PartnerPatternResponse:
    entity = await svc.add_pattern(partner_id, mandant_id, body)
    return PartnerPatternResponse(
        id=entity.id,
        pattern=entity.pattern,
        pattern_type=PartnerPatternType(entity.pattern_type),
        match_field=MatchField(entity.match_field),
        created_at=entity.created_at,
    )


@partners_router.delete(
    "/{mandant_id}/partners/{partner_id}/patterns/{pattern_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_pattern(
    mandant_id: UUID,
    partner_id: UUID,
    pattern_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> None:
    await svc.delete_pattern(pattern_id, partner_id, mandant_id)


@partners_router.post(
    "/{mandant_id}/partners/{partner_id}/patterns/preview",
    response_model=list[PartnerNeighbor],
)
async def preview_pattern(
    mandant_id: UUID,
    partner_id: UUID,
    body: AddPatternRequest,
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerService = Depends(_partner_svc),
) -> list[PartnerNeighbor]:
    return await svc.preview_pattern(partner_id, mandant_id, body)


# ─── Merge endpoint ───────────────────────────────────────────────────────────

@partners_router.post(
    "/{mandant_id}/partners/merge",
    response_model=MergeResponse,
    status_code=status.HTTP_200_OK,
)
async def merge_partners(
    mandant_id: UUID,
    body: MergeRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: PartnerMergeService = Depends(_merge_svc),
) -> MergeResponse:
    return await svc.merge(actor.id, mandant_id, body.source_partner_id, body.target_partner_id)


# ─── Audit-Log endpoints ──────────────────────────────────────────────────────

@partners_router.get(
    "/{mandant_id}/audit-log",
    response_model=PaginatedAuditLogResponse,
    tags=["audit-log"],
)
async def list_audit_log(
    mandant_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: AuditLogService = Depends(_audit_svc),
) -> PaginatedAuditLogResponse:
    return await svc.list_by_mandant(mandant_id, page=page, size=size)
