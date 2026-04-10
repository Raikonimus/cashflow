import math
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.auth.models import User
from app.core.database import get_session
from app.imports.schemas import (
    ImportRunDetailResponse,
    ImportRunListItem,
    PaginatedImportRunsResponse,
)
from app.imports.service import ImportService

imports_router = APIRouter(
    prefix="/mandants/{mandant_id}/accounts/{account_id}/imports",
    tags=["imports"],
)


def _import_svc(session: AsyncSession = Depends(get_session)) -> ImportService:
    return ImportService(session)


@imports_router.post(
    "",
    response_model=list[ImportRunDetailResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_csv(
    mandant_id: UUID,
    account_id: UUID,
    files: list[UploadFile] = File(...),
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ImportService = Depends(_import_svc),
) -> list[ImportRunDetailResponse]:
    runs = await svc.upload(actor.id, account_id, mandant_id, files)
    return [ImportRunDetailResponse.model_validate(r) for r in runs]


@imports_router.get("", response_model=PaginatedImportRunsResponse)
async def list_import_runs(
    mandant_id: UUID,
    account_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: ImportService = Depends(_import_svc),
) -> PaginatedImportRunsResponse:
    items, total = await svc.list_runs(account_id, page=page, size=size)
    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedImportRunsResponse(
        items=[ImportRunListItem.model_validate(r) for r in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@imports_router.get("/{run_id}", response_model=ImportRunDetailResponse)
async def get_import_run(
    mandant_id: UUID,
    account_id: UUID,
    run_id: UUID,
    actor: User = Depends(require_role("viewer")),
    _access: None = Depends(require_mandant_access),
    svc: ImportService = Depends(_import_svc),
) -> ImportRunDetailResponse:
    run = await svc.get_run(run_id, account_id)
    return ImportRunDetailResponse.model_validate(run)
