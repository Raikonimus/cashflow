from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.core.database import get_session
from app.testing.schemas import PartnerAssignmentTestResponse, ServiceAmountConsistencyTestResponse
from app.testing.service import TestingService


testing_router = APIRouter(prefix="/mandants", tags=["testing"])


def _testing_svc(session: AsyncSession = Depends(get_session)) -> TestingService:
    return TestingService(session)


TestingServiceDep = Annotated[TestingService, Depends(_testing_svc)]


@testing_router.post(
    "/{mandant_id}/settings/tests/partner-assignment",
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def run_partner_assignment_test(
    mandant_id: UUID,
    svc: TestingServiceDep,
) -> PartnerAssignmentTestResponse:
    return await svc.run_partner_assignment_consistency_test(mandant_id)


@testing_router.post(
    "/{mandant_id}/settings/tests/service-amount-consistency",
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def run_service_amount_consistency_test(
    mandant_id: UUID,
    svc: TestingServiceDep,
) -> ServiceAmountConsistencyTestResponse:
    return await svc.run_service_amount_consistency_test(mandant_id)
