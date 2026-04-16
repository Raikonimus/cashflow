from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.auth.models import User
from app.core.database import get_session
from app.journal.schemas import AssignServiceRequest, BulkAssignRequest, BulkAssignResponse, IncomeExpenseMatrixResponse, JournalLineResponse, JournalYearsResponse, PaginatedJournalResponse, SORTABLE_COLUMNS
from app.journal.service import JournalService
from app.partners.schemas import PaginatedAuditLogResponse
from app.partners.service import AuditLogService

journal_router = APIRouter(prefix="/mandants", tags=["journal"])
audit_router = APIRouter(prefix="/mandants", tags=["audit"])


def _journal_svc(session: AsyncSession = Depends(get_session)) -> JournalService:
    return JournalService(session)


def _audit_svc(session: AsyncSession = Depends(get_session)) -> AuditLogService:
    return AuditLogService(session)


# ─── Journal Lines ────────────────────────────────────────────────────────────

@journal_router.get(
    "/{mandant_id}/journal",
    response_model=PaginatedJournalResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_journal_lines(
    mandant_id: UUID,
    account_id: UUID | None = Query(default=None),
    partner_id: UUID | None = Query(default=None),
    service_id: UUID | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    has_partner: bool | None = Query(default=None),
    search: str = Query(default=""),
    sort_by: str = Query(default="valuta_date"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    svc: JournalService = Depends(_journal_svc),
) -> PaginatedJournalResponse:
    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "valuta_date"
    return await svc.list_lines(
        mandant_id,
        account_id=account_id,
        partner_id=partner_id,
        service_id=service_id,
        year=year,
        month=month,
        has_partner=has_partner,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )


@journal_router.get(
    "/{mandant_id}/journal/years",
    response_model=JournalYearsResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_journal_years(
    mandant_id: UUID,
    account_id: UUID | None = Query(default=None),
    svc: JournalService = Depends(_journal_svc),
) -> JournalYearsResponse:
    return await svc.list_years(mandant_id, account_id=account_id)


@journal_router.get(
    "/{mandant_id}/reports/income-expense",
    response_model=IncomeExpenseMatrixResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def get_income_expense_matrix(
    mandant_id: UUID,
    year: int = Query(ge=2000, le=2100),
    svc: JournalService = Depends(_journal_svc),
) -> IncomeExpenseMatrixResponse:
    return await svc.get_income_expense_matrix(mandant_id=mandant_id, year=year)


@journal_router.post(
    "/{mandant_id}/journal/bulk-assign",
    response_model=BulkAssignResponse,
)
async def bulk_assign_partner(
    mandant_id: UUID,
    body: BulkAssignRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: JournalService = Depends(_journal_svc),
) -> BulkAssignResponse:
    return await svc.bulk_assign(
        mandant_id,
        actor_id=actor.id,
        line_ids=body.line_ids,
        partner_id=body.partner_id,
    )


@journal_router.post(
    "/{mandant_id}/journal/{line_id}/assign-service",
    response_model=JournalLineResponse,
)
async def assign_service_to_line(
    mandant_id: UUID,
    line_id: UUID,
    body: AssignServiceRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: JournalService = Depends(_journal_svc),
) -> JournalLineResponse:
    return await svc.assign_service(
        mandant_id=mandant_id,
        actor_id=actor.id,
        line_id=line_id,
        service_id=body.service_id,
    )


# ─── Audit Log ────────────────────────────────────────────────────────────────

@audit_router.get(
    "/{mandant_id}/audit",
    response_model=PaginatedAuditLogResponse,
    dependencies=[Depends(require_role("mandant_admin")), Depends(require_mandant_access)],
)
async def list_audit_log(
    mandant_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    svc: AuditLogService = Depends(_audit_svc),
) -> PaginatedAuditLogResponse:
    return await svc.list_by_mandant(mandant_id, page=page, size=size)
