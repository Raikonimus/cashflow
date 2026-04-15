from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.core.database import get_session
from app.testing.schemas import PartnerAssignmentTestResponse
from app.testing.service import TestingService


testing_router = APIRouter(prefix="/mandants", tags=["testing"])


def _testing_svc(session: AsyncSession = Depends(get_session)) -> TestingService:
    return TestingService(session)


@testing_router.post(
    "/{mandant_id}/settings/tests/partner-assignment",
    response_model=PartnerAssignmentTestResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def run_partner_assignment_test(
    mandant_id: UUID,
    svc: TestingService = Depends(_testing_svc),
) -> PartnerAssignmentTestResponse:
    return await svc.run_partner_assignment_consistency_test(mandant_id)
