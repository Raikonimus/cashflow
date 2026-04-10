import math
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.auth.models import User
from app.core.database import get_session
from app.review.schemas import (
    AdjustReviewRequest,
    NewPartnerRequest,
    PaginatedReviewItemsResponse,
    ReassignRequest,
    ReviewItemResponse,
)
from app.review.service import ReviewService

review_router = APIRouter(
    prefix="/mandants/{mandant_id}/review",
    tags=["review"],
)


def _review_svc(session: AsyncSession = Depends(get_session)) -> ReviewService:
    return ReviewService(session)


@review_router.get(
    "",
    response_model=PaginatedReviewItemsResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def list_review_items(
    mandant_id: UUID,
    status_filter: str = Query(default="open", alias="status", description="open | confirmed | adjusted | all"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    svc: ReviewService = Depends(_review_svc),
) -> PaginatedReviewItemsResponse:
    items, total = await svc.list_items(mandant_id, status_filter, page=page, size=size)
    pages = math.ceil(total / size) if total > 0 else 1
    response_items: list[ReviewItemResponse] = []
    for item in items:
        response_items.append(await svc.to_response(item))
    return PaginatedReviewItemsResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@review_router.get(
    "/archive",
    response_model=PaginatedReviewItemsResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def list_review_archive(
    mandant_id: UUID,
    item_type: str | None = Query(default=None),
    resolved_by_user_id: UUID | None = Query(default=None),
    resolved_from: date | None = Query(default=None),
    resolved_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    svc: ReviewService = Depends(_review_svc),
) -> PaginatedReviewItemsResponse:
    items, total = await svc.list_archive(
        mandant_id,
        item_type=item_type,
        resolved_by_user_id=resolved_by_user_id,
        resolved_from=resolved_from,
        resolved_to=resolved_to,
        page=page,
        size=size,
    )
    pages = math.ceil(total / size) if total > 0 else 1
    response_items: list[ReviewItemResponse] = []
    for item in items:
        response_items.append(await svc.to_response(item))
    return PaginatedReviewItemsResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@review_router.get(
    "/{item_id}",
    response_model=ReviewItemResponse,
    status_code=http_status.HTTP_200_OK,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def get_review_item(
    mandant_id: UUID,
    item_id: UUID,
    svc: ReviewService = Depends(_review_svc),
) -> ReviewItemResponse:
    item = await svc.get_item(item_id, mandant_id)
    return await svc.to_response(item)


@review_router.post(
    "/{item_id}/confirm",
    response_model=ReviewItemResponse,
    status_code=http_status.HTTP_200_OK,
)
async def confirm_review_item(
    mandant_id: UUID,
    item_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ReviewService = Depends(_review_svc),
) -> ReviewItemResponse:
    item = await svc.confirm(item_id, mandant_id, actor.id)  # type: ignore[arg-type]
    return await svc.to_response(item)


@review_router.post(
    "/{item_id}/adjust",
    response_model=ReviewItemResponse,
    status_code=http_status.HTTP_200_OK,
)
async def adjust_review_item(
    mandant_id: UUID,
    item_id: UUID,
    body: AdjustReviewRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ReviewService = Depends(_review_svc),
) -> ReviewItemResponse:
    item = await svc.adjust(item_id, mandant_id, actor.id, body)  # type: ignore[arg-type]
    return await svc.to_response(item)


@review_router.post(
    "/{item_id}/reject",
    response_model=ReviewItemResponse,
    status_code=http_status.HTTP_200_OK,
)
async def reject_review_item(
    mandant_id: UUID,
    item_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ReviewService = Depends(_review_svc),
) -> ReviewItemResponse:
    item = await svc.reject(item_id, mandant_id, actor.id)  # type: ignore[arg-type]
    return await svc.to_response(item)


@review_router.post(
    "/{item_id}/reassign",
    response_model=ReviewItemResponse,
    status_code=http_status.HTTP_200_OK,
)
async def reassign_review_item(
    mandant_id: UUID,
    item_id: UUID,
    body: ReassignRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ReviewService = Depends(_review_svc),
) -> ReviewItemResponse:
    item = await svc.reassign(item_id, mandant_id, actor.id, body.partner_id)  # type: ignore[arg-type]
    return await svc.to_response(item)


@review_router.post(
    "/{item_id}/new-partner",
    response_model=ReviewItemResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def new_partner_review_item(
    mandant_id: UUID,
    item_id: UUID,
    body: NewPartnerRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ReviewService = Depends(_review_svc),
) -> ReviewItemResponse:
    item = await svc.create_and_assign(item_id, mandant_id, actor.id, body.name)  # type: ignore[arg-type]
    return await svc.to_response(item)
