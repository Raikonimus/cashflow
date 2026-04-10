from typing import Optional
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import MandantUser, User, UserRole
from app.auth.security import decode_access_token
from app.core.database import get_session

log = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLE_HIERARCHY: dict[str, int] = {
    UserRole.admin.value: 4,
    UserRole.mandant_admin.value: 3,
    UserRole.accountant.value: 2,
    UserRole.viewer.value: 1,
}


async def get_jwt_payload(token: str = Depends(oauth2_scheme)) -> dict:
    """Extract and verify JWT payload without DB lookup."""
    try:
        return decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    payload: dict = Depends(get_jwt_payload),
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id_str: Optional[str] = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await session.get(User, UUID(user_id_str))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(min_role: str):
    """
    Dependency factory: ensures the current user has at least `min_role`.

    Usage:
        @router.post("/...", dependencies=[Depends(require_role("accountant"))])
        async def endpoint(current_user: User = Depends(require_role("accountant"))):
    """

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(min_role, 999)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return current_user

    return dependency


async def require_mandant_access(
    mandant_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Verify current user has access to the given mandant.
    Admin bypasses this check (ADR-001 / RBAC design).
    """
    if current_user.role == UserRole.admin.value:
        return

    result = await session.exec(
        select(MandantUser).where(
            MandantUser.user_id == current_user.id,
            MandantUser.mandant_id == mandant_id,
        )
    )
    if result.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to mandant denied",
        )
