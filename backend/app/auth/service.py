from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.email import send_invitation_email, send_password_reset_email
from app.auth.models import Mandant, MandantUser, PasswordResetToken, User, UserInvitation, UserRole
from app.auth.security import (
    create_access_token,
    generate_raw_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.config import settings
from app.partners.models import AuditLog

log = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    # DB values may be naive while tests can inject aware timestamps.
    # Normalize both to UTC-naive before comparisons.
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def login(self, email: str, password: str) -> dict:
        user = await self._get_user_by_email(email)

        # Constant-time failure path: always attempt verify even if user not found
        dummy_hash = "$2b$12$mqi/bTXx0seaYIZVL7lMRO1AtXJ/thdGanrdd.l/pZNsH90CtedI2"
        if user is None:
            verify_password(password, dummy_hash)
            log.warning("login_failed", email=email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account disabled",
            )

        if user.password_hash is None:
            verify_password(password, dummy_hash)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invitation pending – set your password first",
            )

        if not verify_password(password, user.password_hash):
            log.warning("login_failed", email=email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        mandants = await self._get_mandants_for_user(user.id)

        # Admin: no mandant restriction (ADR-001)
        if user.role == UserRole.admin.value:
            token = create_access_token(
                {"sub": str(user.id), "role": user.role, "mandant_id": None}
            )
            await self._write_audit(user.id, None, "auth.login", {"email": email, "role": user.role})
            return {"access_token": token, "mandants": mandants, "requires_mandant_selection": False}

        # Exactly 1 mandant: embed mandant_id in token directly
        if len(mandants) == 1:
            token = create_access_token(
                {"sub": str(user.id), "role": user.role, "mandant_id": str(mandants[0].id)}
            )
            await self._write_audit(user.id, mandants[0].id, "auth.login", {"email": email, "role": user.role})
            return {"access_token": token, "mandants": mandants, "requires_mandant_selection": False}

        # Multiple mandants: client must call /select-mandant
        token = create_access_token(
            {"sub": str(user.id), "role": user.role, "mandant_id": None}
        )
        await self._write_audit(user.id, None, "auth.login", {"email": email, "role": user.role, "mandants": len(mandants)})
        return {
            "access_token": token,
            "mandants": mandants,
            "requires_mandant_selection": len(mandants) > 1,
        }

    async def select_mandant(self, user: User, mandant_id: UUID) -> str:
        if user.role != UserRole.admin.value:
            result = await self.session.exec(
                select(MandantUser).where(
                    MandantUser.user_id == user.id,
                    MandantUser.mandant_id == mandant_id,
                )
            )
            if result.first() is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to mandant denied",
                )

        return create_access_token(
            {"sub": str(user.id), "role": user.role, "mandant_id": str(mandant_id)}
        )

    async def logout(self, user: User, mandant_id: Optional[UUID]) -> None:
        await self._write_audit(user.id, mandant_id, "auth.logout", {"email": user.email, "role": user.role})

    async def _write_audit(self, actor_id: UUID, mandant_id: Optional[UUID], event_type: str, payload: dict) -> None:
        entry = AuditLog(mandant_id=mandant_id, event_type=event_type, actor_id=actor_id, payload=payload)
        self.session.add(entry)
        await self.session.commit()
        log.info("audit", event_type=event_type, actor_id=str(actor_id))

    async def _get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.session.exec(
            select(User).where(User.email == email.lower())
        )
        return result.first()

    async def _get_mandants_for_user(self, user_id: UUID) -> list[Mandant]:
        result = await self.session.exec(
            select(Mandant)
            .join(MandantUser, Mandant.id == MandantUser.mandant_id)
            .where(MandantUser.user_id == user_id, Mandant.is_active == True)  # noqa: E712
        )
        return list(result.all())


class PasswordResetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request_reset(self, email: str) -> None:
        """
        Request a password reset link. Always succeeds silently – no email enumeration.
        """
        result = await self.session.exec(
            select(User).where(User.email == email.lower())
        )
        user = result.first()

        if user is None:
            return  # Silent no-op (story 002: always return 200)

        raw_token = generate_raw_token()
        token_hash_val = hash_token(raw_token)
        expires_at = _utcnow() + timedelta(minutes=60)

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash_val,
            expires_at=expires_at,
        )
        self.session.add(reset_token)
        await self.session.commit()

        reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
        await send_password_reset_email(user.email, reset_url)

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        incoming_hash = hash_token(raw_token)

        result = await self.session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == incoming_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > _utcnow(),
            )
        )
        reset_token = result.first()

        if reset_token is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token expired or invalid",
            )

        user = await self.session.get(User, reset_token.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token",
            )

        user.password_hash = hash_password(new_password)
        user.updated_at = _utcnow()
        reset_token.used_at = _utcnow()

        # Invalidate all remaining unused tokens for this user
        other_tokens_result = await self.session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == reset_token.user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.id != reset_token.id,
            )
        )
        for old_token in other_tokens_result.all():
            old_token.used_at = _utcnow()
            self.session.add(old_token)

        self.session.add(user)
        self.session.add(reset_token)
        await self.session.commit()


ROLES_MANDANT_ADMIN_CAN_CREATE = {UserRole.accountant.value, UserRole.viewer.value}


class UserManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_users(self, actor: User) -> list[User]:
        if actor.role == UserRole.admin.value:
            result = await self.session.exec(select(User).order_by(User.email))
            return list(result.all())
        # mandant_admin: only users sharing a mandant
        actor_mandants = await self.session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == actor.id)
        )
        mandant_ids = list(actor_mandants.all())
        if not mandant_ids:
            return []
        result = await self.session.exec(
            select(User)
            .join(MandantUser, User.id == MandantUser.user_id)
            .where(MandantUser.mandant_id.in_(mandant_ids))
            .order_by(User.email)
        )
        return list(result.unique().all())

    async def create_user(self, actor: User, email: str, role: str) -> User:
        # Role permission check
        if actor.role == UserRole.mandant_admin.value and role not in ROLES_MANDANT_ADMIN_CAN_CREATE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to assign this role",
            )
        if actor.role not in (UserRole.admin.value, UserRole.mandant_admin.value):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

        # Duplicate check
        existing = await self.session.exec(select(User).where(User.email == email.lower()))
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        user = User(email=email.lower(), role=role)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        # Fire invitation – SMTP failure must NOT roll back user creation (ADR-004)
        invitation_svc = InvitationService(self.session)
        await invitation_svc.send_invitation(user)

        return user

    async def get_user(self, actor: User, user_id: UUID) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        await self._check_mandant_access(actor, user)
        return user

    async def update_user(self, actor: User, user_id: UUID, patch: dict) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        await self._check_mandant_access(actor, user)

        if "role" in patch and patch["role"] is not None:
            new_role = patch["role"].value if hasattr(patch["role"], "value") else patch["role"]
            if actor.role == UserRole.mandant_admin.value and new_role not in ROLES_MANDANT_ADMIN_CAN_CREATE:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
            user.role = new_role

        if "email" in patch and patch["email"] is not None:
            user.email = str(patch["email"]).lower()
        if "is_active" in patch and patch["is_active"] is not None:
            user.is_active = patch["is_active"]

        user.updated_at = _utcnow()
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def _check_mandant_access(self, actor: User, target: User) -> None:
        if actor.role == UserRole.admin.value:
            return
        # Mandant-Admin: both actor and target must share a mandant
        actor_mandants = await self.session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == actor.id)
        )
        actor_mandant_ids = {r for r in actor_mandants.all()}

        target_mandants = await self.session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == target.id)
        )
        target_mandant_ids = {r for r in target_mandants.all()}

        if not actor_mandant_ids.intersection(target_mandant_ids):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    async def delete_user(self, actor: User, user_id: UUID) -> None:
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if str(user.id) == str(actor.id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
        await self._check_mandant_access(actor, user)
        await self.session.delete(user)
        await self.session.commit()


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def send_invitation(self, user: User) -> UserInvitation:
        # Invalidate all pending invitations for this user
        await self._invalidate_pending(user.id)

        raw_token = generate_raw_token()
        expires_at = _utcnow() + timedelta(days=settings.invitation_expire_days)
        invitation = UserInvitation(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        self.session.add(invitation)
        await self.session.commit()
        await self.session.refresh(invitation)

        invite_url = f"{settings.frontend_url}/accept-invitation?token={raw_token}"
        # SMTP failure swallowed – user already created (ADR-004)
        await send_invitation_email(user.email, invite_url, settings.invitation_expire_days)
        return invitation

    async def accept_invitation(self, raw_token: str, password: str) -> None:
        incoming_hash = hash_token(raw_token)
        result = await self.session.exec(
            select(UserInvitation).where(
                UserInvitation.token_hash == incoming_hash,
                UserInvitation.accepted_at.is_(None),
            )
        )
        invitation = result.first()

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token",
            )
        if _as_utc_naive(invitation.expires_at) <= _utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation expired",
            )

        user = await self.session.get(User, invitation.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

        user.password_hash = hash_password(password)
        user.updated_at = _utcnow()
        invitation.accepted_at = _utcnow()

        self.session.add(user)
        self.session.add(invitation)
        await self.session.commit()

    async def get_invitation_status(self, user_id: UUID) -> str:
        result = await self.session.exec(
            select(UserInvitation)
            .where(UserInvitation.user_id == user_id)
            .order_by(UserInvitation.created_at.desc())
        )
        invitation = result.first()
        if invitation is None:
            return "accepted"  # Pre-invitation users (e.g. seeded admin)
        if invitation.accepted_at is not None:
            return "accepted"
        if _as_utc_naive(invitation.expires_at) <= _utcnow():
            return "expired"
        return "pending"

    async def _invalidate_pending(self, user_id: UUID) -> None:
        result = await self.session.exec(
            select(UserInvitation).where(
                UserInvitation.user_id == user_id,
                UserInvitation.accepted_at.is_(None),
            )
        )
        for inv in result.all():
            inv.accepted_at = _utcnow()  # mark as "used" to invalidate
            self.session.add(inv)
        await self.session.commit()


class MandantAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def assign_user(self, mandant_id: UUID, user_id: UUID) -> MandantUser:
        # Verify both exist
        mandant = await self.session.get(Mandant, mandant_id)
        if mandant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant not found")
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        existing = await self.session.exec(
            select(MandantUser).where(
                MandantUser.mandant_id == mandant_id,
                MandantUser.user_id == user_id,
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already assigned to this mandant",
            )

        mu = MandantUser(mandant_id=mandant_id, user_id=user_id)
        self.session.add(mu)
        await self.session.commit()
        await self.session.refresh(mu)
        return mu

    async def unassign_user(self, mandant_id: UUID, user_id: UUID) -> None:
        result = await self.session.exec(
            select(MandantUser).where(
                MandantUser.mandant_id == mandant_id,
                MandantUser.user_id == user_id,
            )
        )
        mu = result.first()
        if mu is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
            )
        await self.session.delete(mu)
        await self.session.commit()
