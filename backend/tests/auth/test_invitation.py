"""
Integration tests – Invitation flow
POST /api/v1/auth/accept-invitation
POST /api/v1/users/:id/resend-invitation
(Story 006-user-invitation)
"""
import pytest

from tests.auth.conftest import assign_user_to_mandant, create_mandant, create_user
from app.auth.models import UserInvitation, UserRole
from app.auth.security import generate_raw_token, hash_token


async def _admin_token(client, db_session) -> str:
    await create_user(db_session, email="admin@test.com", role=UserRole.admin)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "admin@test.com", "password": "secret123"}
    )
    return resp.json()["access_token"]


async def _create_invited_user(client, token: str, email: str = "invited@example.com") -> dict:
    resp = await client.post(
        "/api/v1/users",
        json={"email": email, "role": "viewer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


async def _get_raw_token_from_db(db_session, user_id) -> str:
    """Helper: generate + insert a valid invitation token directly."""
    from datetime import datetime, timedelta, timezone
    raw = generate_raw_token()
    inv = UserInvitation(
        user_id=user_id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(inv)
    await db_session.commit()
    return raw


class TestCreateUserSendsInvitation:
    async def test_new_user_has_pending_invitation_status(self, client, db_session):
        token = await _admin_token(client, db_session)
        data = await _create_invited_user(client, token)
        assert data["invitation_status"] == "pending"

    async def test_new_user_has_no_password(self, client, db_session):
        from sqlmodel import select
        from app.auth.models import User

        token = await _admin_token(client, db_session)
        data = await _create_invited_user(client, token)

        result = await db_session.exec(select(User).where(User.email == "invited@example.com"))
        user = result.first()
        assert user.password_hash is None

    async def test_pending_user_cannot_login(self, client, db_session):
        token = await _admin_token(client, db_session)
        await _create_invited_user(client, token)

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "invited@example.com", "password": "anything"},
        )
        assert resp.status_code == 401
        assert "Invitation" in resp.json()["detail"]


class TestAcceptInvitation:
    async def test_accept_with_valid_token_sets_password(self, client, db_session):
        token = await _admin_token(client, db_session)
        user_data = await _create_invited_user(client, token)

        from sqlmodel import select
        from app.auth.models import User
        result = await db_session.exec(
            select(User).where(User.email == "invited@example.com")
        )
        user = result.first()

        # Clear existing invitation and insert one we control
        from sqlmodel import select as sel
        from app.auth.models import UserInvitation
        invs = await db_session.exec(sel(UserInvitation).where(UserInvitation.user_id == user.id))
        for inv in invs.all():
            await db_session.delete(inv)
        await db_session.commit()

        raw = await _get_raw_token_from_db(db_session, user.id)

        resp = await client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": raw, "password": "NewPassword1"},
        )
        assert resp.status_code == 200

        # Now login works
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "invited@example.com", "password": "NewPassword1"},
        )
        assert login.status_code == 200

    async def test_accept_with_expired_token_returns_400(self, client, db_session):
        from datetime import datetime, timedelta, timezone
        token = await _admin_token(client, db_session)
        user_data = await _create_invited_user(client, token)

        from sqlmodel import select
        from app.auth.models import User, UserInvitation
        result = await db_session.exec(
            select(User).where(User.email == "invited@example.com")
        )
        user = result.first()

        # Clear and insert expired token
        invs = await db_session.exec(select(UserInvitation).where(UserInvitation.user_id == user.id))
        for inv in invs.all():
            await db_session.delete(inv)
        await db_session.commit()

        raw = generate_raw_token()
        expired_inv = UserInvitation(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db_session.add(expired_inv)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": raw, "password": "NewPassword1"},
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    async def test_accept_already_used_token_returns_400(self, client, db_session):
        from datetime import datetime, timedelta, timezone
        from app.auth.models import User, UserInvitation
        from sqlmodel import select

        token = await _admin_token(client, db_session)
        await _create_invited_user(client, token)

        result = await db_session.exec(
            select(User).where(User.email == "invited@example.com")
        )
        user = result.first()

        invs = await db_session.exec(select(UserInvitation).where(UserInvitation.user_id == user.id))
        for inv in invs.all():
            await db_session.delete(inv)
        await db_session.commit()

        raw = await _get_raw_token_from_db(db_session, user.id)

        # Accept once
        await client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": raw, "password": "Password123"},
        )
        # Accept again
        resp = await client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": raw, "password": "Password123"},
        )
        assert resp.status_code == 400

    async def test_invalid_token_returns_400(self, client, db_session):
        resp = await client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": "totallywrong", "password": "Password123"},
        )
        assert resp.status_code == 400


class TestResendInvitation:
    async def test_resend_creates_new_invitation(self, client, db_session):
        from sqlmodel import select
        from app.auth.models import User, UserInvitation

        adm_token = await _admin_token(client, db_session)
        user_data = await _create_invited_user(client, adm_token)

        result = await db_session.exec(
            select(User).where(User.email == "invited@example.com")
        )
        user = result.first()

        resp = await client.post(
            f"/api/v1/users/{user.id}/resend-invitation",
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 200

    async def test_resend_for_accepted_user_returns_400(self, client, db_session):
        from sqlmodel import select
        from app.auth.models import User, UserInvitation

        adm_token = await _admin_token(client, db_session)
        await _create_invited_user(client, adm_token)

        result = await db_session.exec(
            select(User).where(User.email == "invited@example.com")
        )
        user = result.first()

        # Mark invitation as accepted directly
        invs = await db_session.exec(
            select(UserInvitation).where(UserInvitation.user_id == user.id)
        )
        from datetime import datetime, timezone
        for inv in invs.all():
            inv.accepted_at = datetime.now(timezone.utc)
            db_session.add(inv)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/users/{user.id}/resend-invitation",
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 400
        assert "already accepted" in resp.json()["detail"].lower()
