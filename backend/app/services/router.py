from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_mandant_access, require_role
from app.core.database import get_session
from app.services.schemas import (
    AssignServiceGroupRequest,
    CreateServiceMatcherRequest,
    CreateServiceRequest,
    CreateServiceGroupRequest,
    CreateServiceTypeKeywordRequest,
    DeleteServiceGroupRequest,
    MatcherPreviewResponse,
    ServiceGroupAssignmentResponse,
    ServiceGroupResponse,
    ServiceMatcherResponse,
    ServiceResponse,
    ServiceTypeKeywordListResponse,
    ServiceTypeKeywordResponse,
    UpdateServiceGroupRequest,
    UpdateServiceMatcherRequest,
    UpdateServiceRequest,
    UpdateServiceTypeKeywordRequest,
)
from app.services.models import ServiceGroupSection
from app.services.service import ServiceManagementService

services_router = APIRouter(prefix="/mandants", tags=["services"])


def _services_svc(session: AsyncSession = Depends(get_session)) -> ServiceManagementService:
    return ServiceManagementService(session)


@services_router.get(
    "/{mandant_id}/partners/{partner_id}/services",
    response_model=list[ServiceResponse],
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_services(
    mandant_id: UUID,
    partner_id: UUID,
    svc: ServiceManagementService = Depends(_services_svc),
) -> list[ServiceResponse]:
    return await svc.list_services(partner_id, mandant_id)


@services_router.post(
    "/{mandant_id}/partners/{partner_id}/services",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def create_service(
    mandant_id: UUID,
    partner_id: UUID,
    body: CreateServiceRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceResponse:
    return await svc.create_service(partner_id, mandant_id, body)


@services_router.patch(
    "/{mandant_id}/services/{service_id}",
    response_model=ServiceResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def update_service(
    mandant_id: UUID,
    service_id: UUID,
    body: UpdateServiceRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceResponse:
    return await svc.update_service(service_id, mandant_id, body)


@services_router.delete(
    "/{mandant_id}/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def delete_service(
    mandant_id: UUID,
    service_id: UUID,
    svc: ServiceManagementService = Depends(_services_svc),
) -> None:
    await svc.delete_service(service_id, mandant_id)


@services_router.post(
    "/{mandant_id}/services/{service_id}/matchers",
    response_model=ServiceMatcherResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def create_matcher(
    mandant_id: UUID,
    service_id: UUID,
    body: CreateServiceMatcherRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceMatcherResponse:
    matcher = await svc.create_matcher(service_id, mandant_id, body)
    return ServiceMatcherResponse.model_validate(matcher)


@services_router.patch(
    "/{mandant_id}/services/{service_id}/matchers/{matcher_id}",
    response_model=ServiceMatcherResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def update_matcher(
    mandant_id: UUID,
    service_id: UUID,
    matcher_id: UUID,
    body: UpdateServiceMatcherRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceMatcherResponse:
    matcher = await svc.update_matcher(service_id, matcher_id, mandant_id, body)
    return ServiceMatcherResponse.model_validate(matcher)


@services_router.delete(
    "/{mandant_id}/services/{service_id}/matchers/{matcher_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def delete_matcher(
    mandant_id: UUID,
    service_id: UUID,
    matcher_id: UUID,
    svc: ServiceManagementService = Depends(_services_svc),
) -> None:
    await svc.delete_matcher(service_id, matcher_id, mandant_id)


@services_router.post(
    "/{mandant_id}/services/{service_id}/matchers/preview",
    response_model=MatcherPreviewResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def preview_matcher(
    mandant_id: UUID,
    service_id: UUID,
    body: CreateServiceMatcherRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> MatcherPreviewResponse:
    return await svc.preview_matcher(service_id, mandant_id, body)


@services_router.get(
    "/{mandant_id}/settings/service-keywords",
    response_model=ServiceTypeKeywordListResponse,
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_service_keywords(
    mandant_id: UUID,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceTypeKeywordListResponse:
    return await svc.list_keywords(mandant_id)


@services_router.post(
    "/{mandant_id}/settings/service-keywords",
    response_model=ServiceTypeKeywordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def create_service_keyword(
    mandant_id: UUID,
    body: CreateServiceTypeKeywordRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceTypeKeywordResponse:
    return await svc.create_keyword(mandant_id, body)


@services_router.patch(
    "/{mandant_id}/settings/service-keywords/{keyword_id}",
    response_model=ServiceTypeKeywordResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def update_service_keyword(
    mandant_id: UUID,
    keyword_id: UUID,
    body: UpdateServiceTypeKeywordRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceTypeKeywordResponse:
    return await svc.update_keyword(mandant_id, keyword_id, body)


@services_router.delete(
    "/{mandant_id}/settings/service-keywords/{keyword_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def delete_service_keyword(
    mandant_id: UUID,
    keyword_id: UUID,
    svc: ServiceManagementService = Depends(_services_svc),
) -> None:
    await svc.delete_keyword(mandant_id, keyword_id)


@services_router.get(
    "/{mandant_id}/service-groups",
    response_model=list[ServiceGroupResponse],
    dependencies=[Depends(require_role("viewer")), Depends(require_mandant_access)],
)
async def list_service_groups(
    mandant_id: UUID,
    section: ServiceGroupSection,
    svc: ServiceManagementService = Depends(_services_svc),
) -> list[ServiceGroupResponse]:
    return await svc.list_service_groups(mandant_id, section)


@services_router.post(
    "/{mandant_id}/service-groups",
    response_model=ServiceGroupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def create_service_group(
    mandant_id: UUID,
    body: CreateServiceGroupRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceGroupResponse:
    return await svc.create_service_group(mandant_id, body)


@services_router.patch(
    "/{mandant_id}/service-groups/{group_id}",
    response_model=ServiceGroupResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def update_service_group(
    mandant_id: UUID,
    group_id: UUID,
    body: UpdateServiceGroupRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceGroupResponse:
    return await svc.update_service_group(mandant_id, group_id, body)


@services_router.delete(
    "/{mandant_id}/service-groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def delete_service_group(
    mandant_id: UUID,
    group_id: UUID,
    body: DeleteServiceGroupRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> None:
    await svc.delete_service_group(mandant_id, group_id, body)


@services_router.post(
    "/{mandant_id}/services/{service_id}/group-assignment",
    response_model=ServiceGroupAssignmentResponse,
    dependencies=[Depends(require_role("accountant")), Depends(require_mandant_access)],
)
async def assign_service_group(
    mandant_id: UUID,
    service_id: UUID,
    body: AssignServiceGroupRequest,
    svc: ServiceManagementService = Depends(_services_svc),
) -> ServiceGroupAssignmentResponse:
    return await svc.assign_service_group(mandant_id, service_id, body.service_group_id)
