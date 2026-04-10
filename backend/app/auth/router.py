from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_jwt_payload, require_role
from app.auth.models import User, UserRole
from app.auth.schemas import (
    AcceptInvitationRequest,
    CreateUserRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MandantInfo,
    MandantUserAssignRequest,
    MandantUserResponse,
    MessageResponse,
    ResetPasswordRequest,
    SelectMandantRequest,
    TokenResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserResponse,
)
from app.auth.service import (
    AuthService,
    InvitationService,
    MandantAssignmentService,
    PasswordResetService,
    UserManagementService,
)
from app.core.database import get_session

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])
mandants_router = APIRouter(prefix="/mandants", tags=["mandants"])


# ─── Dependency factories ───────────────────────────────────────────────────

def _auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(session)


def _reset_service(session: AsyncSession = Depends(get_session)) -> PasswordResetService:
    return PasswordResetService(session)


def _user_mgmt_service(session: AsyncSession = Depends(get_session)) -> UserManagementService:
    return UserManagementService(session)


def _invitation_service(session: AsyncSession = Depends(get_session)) -> InvitationService:
    return InvitationService(session)


def _mandant_assignment_service(session: AsyncSession = Depends(get_session)) -> MandantAssignmentService:
    return MandantAssignmentService(session)


# ─── Auth endpoints ──────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    svc: AuthService = Depends(_auth_service),
) -> LoginResponse:
    result = await svc.login(req.email, req.password)
    return LoginResponse(
        access_token=result["access_token"],
        mandants=[MandantInfo(id=m.id, name=m.name) for m in result["mandants"]],
        requires_mandant_selection=result["requires_mandant_selection"],
    )


@router.post("/select-mandant", response_model=TokenResponse)
async def select_mandant(
    req: SelectMandantRequest,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> TokenResponse:
    token = await svc.select_mandant(current_user, req.mandant_id)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: dict = Depends(get_jwt_payload),
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> None:
    mandant_id: Optional[UUID] = None
    raw = payload.get("mandant_id")
    if raw:
        try:
            mandant_id = UUID(raw)
        except (ValueError, AttributeError):
            pass
    await svc.logout(current_user, mandant_id)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    req: ForgotPasswordRequest,
    svc: PasswordResetService = Depends(_reset_service),
) -> MessageResponse:
    await svc.request_reset(req.email)
    return MessageResponse(message="If this email exists, a reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    req: ResetPasswordRequest,
    svc: PasswordResetService = Depends(_reset_service),
) -> MessageResponse:
    await svc.reset_password(req.token, req.password)
    return MessageResponse(message="Password updated successfully")


@router.post("/accept-invitation", response_model=MessageResponse)
async def accept_invitation(
    req: AcceptInvitationRequest,
    svc: InvitationService = Depends(_invitation_service),
) -> MessageResponse:
    await svc.accept_invitation(req.token, req.password)
    return MessageResponse(message="Invitation accepted. You can now log in.")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    payload: dict = Depends(get_jwt_payload),
) -> UserResponse:
    mandant_id_str: Optional[str] = payload.get("mandant_id")
    mandant_id = UUID(mandant_id_str) if mandant_id_str else None
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=UserRole(current_user.role),
        mandant_id=mandant_id,
        is_active=current_user.is_active,
    )


# ─── User management endpoints ───────────────────────────────────────────────

@users_router.get("", response_model=list[UserDetailResponse])
async def list_users(
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
) -> list[UserDetailResponse]:
    users = await svc.list_users(actor)
    result = []
    for user in users:
        inv_status = await inv_svc.get_invitation_status(user.id)
        result.append(UserDetailResponse(
            id=user.id,
            email=user.email,
            role=UserRole(user.role),
            is_active=user.is_active,
            invitation_status=inv_status,
        ))
    return result


@users_router.post("", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: CreateUserRequest,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
) -> UserDetailResponse:
    user = await svc.create_user(actor, str(req.email), req.role.value)
    inv_status = await inv_svc.get_invitation_status(user.id)
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
        invitation_status=inv_status,
    )


@users_router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
) -> UserDetailResponse:
    user = await svc.get_user(actor, user_id)
    inv_status = await inv_svc.get_invitation_status(user.id)
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
        invitation_status=inv_status,
    )


@users_router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: UUID,
    req: UpdateUserRequest,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
) -> UserDetailResponse:
    user = await svc.update_user(actor, user_id, req.model_dump(exclude_unset=True))
    inv_status = await inv_svc.get_invitation_status(user.id)
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
        invitation_status=inv_status,
    )


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
) -> None:
    await svc.delete_user(actor, user_id)


@users_router.post("/{user_id}/resend-invitation", response_model=MessageResponse)
async def resend_invitation(
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
) -> MessageResponse:
    user = await svc.get_user(actor, user_id)
    # Check if already accepted
    inv_status = await inv_svc.get_invitation_status(user.id)
    if inv_status == "accepted":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has already accepted their invitation",
        )
    await inv_svc.send_invitation(user)
    return MessageResponse(message="Invitation resent")


# ─── Mandant assignment endpoints (Admin only) ────────────────────────────────

@mandants_router.post("/{mandant_id}/users", response_model=MandantUserResponse, status_code=status.HTTP_201_CREATED)
async def assign_user_to_mandant(
    mandant_id: UUID,
    req: MandantUserAssignRequest,
    _actor: User = Depends(require_role("admin")),
    svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> MandantUserResponse:
    mu = await svc.assign_user(mandant_id, req.user_id)
    return MandantUserResponse(
        mandant_id=mu.mandant_id,
        user_id=mu.user_id,
        created_at=mu.created_at,
    )


@mandants_router.delete("/{mandant_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_user_from_mandant(
    mandant_id: UUID,
    user_id: UUID,
    _actor: User = Depends(require_role("admin")),
    svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> None:
    await svc.unassign_user(mandant_id, user_id)
