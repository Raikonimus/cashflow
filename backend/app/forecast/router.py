from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.auth.models import User
from app.core.database import get_session
from app.forecast.schemas import (
    CreatePlannedItemRequest,
    CreateSnapshotRequest,
    ForecastOverviewResponse,
    ForecastRuleResponse,
    PlannedItemResponse,
    SnapshotDetail,
    SnapshotSummary,
    UpdateForecastRuleRequest,
    UpdatePlannedItemRequest,
)
from app.forecast.rules import Scenario
from app.forecast.service import ForecastService
from app.journal.service import JournalService

forecast_router = APIRouter(prefix="/mandants", tags=["forecast"])


def _forecast_svc(session: AsyncSession = Depends(get_session)) -> ForecastService:
    return ForecastService(session)


def _journal_svc(session: AsyncSession = Depends(get_session)) -> JournalService:
    return JournalService(session)


# ─── Übersicht ────────────────────────────────────────────────────────────────


@forecast_router.get(
    "/{mandant_id}/forecast/services",
    response_model=ForecastOverviewResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_forecast_services(
    mandant_id: UUID,
    only_without_rule: bool = Query(default=False),
    search: str = Query(default=""),
    svc: ForecastService = Depends(_forecast_svc),
) -> ForecastOverviewResponse:
    return await svc.overview(
        mandant_id, only_without_rule=only_without_rule, search=search
    )


# ─── Regel je Leistung ────────────────────────────────────────────────────────


@forecast_router.get(
    "/{mandant_id}/services/{service_id}/forecast-rule",
    response_model=ForecastRuleResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def get_forecast_rule(
    mandant_id: UUID,
    service_id: UUID,
    svc: ForecastService = Depends(_forecast_svc),
) -> ForecastRuleResponse:
    return await svc.get_rule(mandant_id, service_id)


@forecast_router.put(
    "/{mandant_id}/services/{service_id}/forecast-rule",
    response_model=ForecastRuleResponse,
)
async def set_forecast_rule(
    mandant_id: UUID,
    service_id: UUID,
    body: UpdateForecastRuleRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
) -> ForecastRuleResponse:
    return await svc.set_rule(mandant_id, service_id, body, actor_id=actor.id)


@forecast_router.delete(
    "/{mandant_id}/services/{service_id}/forecast-rule",
    response_model=ForecastRuleResponse,
)
async def reset_forecast_rule(
    mandant_id: UUID,
    service_id: UUID,
    _actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
) -> ForecastRuleResponse:
    return await svc.delete_rule(mandant_id, service_id)


# ─── Planposten ───────────────────────────────────────────────────────────────


@forecast_router.get(
    "/{mandant_id}/forecast/planned-items",
    response_model=list[PlannedItemResponse],
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_planned_items(
    mandant_id: UUID,
    service_id: UUID | None = Query(default=None),
    svc: ForecastService = Depends(_forecast_svc),
) -> list[PlannedItemResponse]:
    return await svc.list_planned_items(mandant_id, service_id)


@forecast_router.post(
    "/{mandant_id}/forecast/planned-items",
    response_model=PlannedItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_planned_item(
    mandant_id: UUID,
    body: CreatePlannedItemRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
) -> PlannedItemResponse:
    return await svc.create_planned_item(mandant_id, body, actor_id=actor.id)


@forecast_router.patch(
    "/{mandant_id}/forecast/planned-items/{item_id}",
    response_model=PlannedItemResponse,
)
async def update_planned_item(
    mandant_id: UUID,
    item_id: UUID,
    body: UpdatePlannedItemRequest,
    _actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
) -> PlannedItemResponse:
    return await svc.update_planned_item(mandant_id, item_id, body)


@forecast_router.delete(
    "/{mandant_id}/forecast/planned-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_planned_item(
    mandant_id: UUID,
    item_id: UUID,
    _actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
) -> None:
    await svc.delete_planned_item(mandant_id, item_id)


# ─── Plan-Ist-Snapshots ───────────────────────────────────────────────────────


@forecast_router.get(
    "/{mandant_id}/forecast/snapshots",
    response_model=list[SnapshotSummary],
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_snapshots(
    mandant_id: UUID,
    svc: ForecastService = Depends(_forecast_svc),
) -> list[SnapshotSummary]:
    return await svc.list_snapshots(mandant_id)


@forecast_router.post(
    "/{mandant_id}/forecast/snapshots",
    response_model=SnapshotDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    mandant_id: UUID,
    body: CreateSnapshotRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
    journal: JournalService = Depends(_journal_svc),
) -> SnapshotDetail:
    """Friert die aktuelle Liquiditätsprognose als Planstand ein.

    Die Prognose wird hier einmal gerechnet und unverändert weitergereicht, damit der
    Snapshot genau das festhält, was in diesem Moment auch die Kurve zeigt.
    """
    try:
        scenario = Scenario(body.scenario)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"scenario must be one of {[item.value for item in Scenario]}",
        ) from None
    liquidity = await journal.get_liquidity(mandant_id, scenario=scenario)
    return await svc.create_snapshot(mandant_id, body, liquidity, actor_id=actor.id)


@forecast_router.get(
    "/{mandant_id}/forecast/snapshots/{snapshot_id}",
    response_model=SnapshotDetail,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def get_snapshot(
    mandant_id: UUID,
    snapshot_id: UUID,
    svc: ForecastService = Depends(_forecast_svc),
) -> SnapshotDetail:
    return await svc.get_snapshot(mandant_id, snapshot_id)


@forecast_router.delete(
    "/{mandant_id}/forecast/snapshots/{snapshot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_snapshot(
    mandant_id: UUID,
    snapshot_id: UUID,
    _actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: ForecastService = Depends(_forecast_svc),
) -> None:
    await svc.delete_snapshot(mandant_id, snapshot_id)
