"""
Integration tests – POST /api/v1/auth/forgot-password
                    POST /api/v1/auth/reset-password
(Story 002-password-reset)
"""
import pytest

from tests.auth.conftest import create_user
from app.auth.models import PasswordResetToken
from app.auth.security import generate_raw_token, hash_token


class TestForgotPassword:
    async def test_always_returns_200_known_email(self, client, db_session):
        await create_user(db_session)
        resp = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "test@example.com"}
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    async def test_always_returns_200_unknown_email(self, client, db_session):
        """No email enumeration: unknown email still returns 200 (ADR privacy)."""
        resp = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
        )
        assert resp.status_code == 200

    async def test_token_is_created_in_db(self, client, db_session):
        await create_user(db_session)
        await client.post(
            "/api/v1/auth/forgot-password", json={"email": "test@example.com"}
        )
        from sqlmodel import select
        result = await db_session.exec(select(PasswordResetToken))
        tokens = result.all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None


class TestResetPassword:
    async def _create_token(self, db_session, user) -> str:
        """Helper: create a valid reset token and return the raw token."""
        from datetime import datetime, timedelta, timezone

        raw = generate_raw_token()
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(token)
        await db_session.commit()
        return raw

    async def test_valid_token_resets_password(self, client, db_session):
        user = await create_user(db_session)
        raw = await self._create_token(db_session, user)

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "NewPassword99"},
        )
        assert resp.status_code == 200

        # New password must work for login
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "NewPassword99"},
        )
        assert login.status_code == 200

    async def test_old_password_no_longer_works(self, client, db_session):
        user = await create_user(db_session)
        raw = await self._create_token(db_session, user)

        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "NewPassword99"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "secret123"},  # old
        )
        assert login.status_code == 401

    async def test_token_is_marked_used(self, client, db_session):
        user = await create_user(db_session)
        raw = await self._create_token(db_session, user)

        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "NewPassword99"},
        )
        from sqlmodel import select
        result = await db_session.exec(select(PasswordResetToken))
        for t in result.all():
            assert t.used_at is not None

    async def test_second_use_of_same_token_fails(self, client, db_session):
        user = await create_user(db_session)
        raw = await self._create_token(db_session, user)

        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "NewPassword99"},
        )
        # Second attempt with same token
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "AnotherPass1"},
        )
        assert resp.status_code == 400

    async def test_invalid_token_returns_400(self, client, db_session):
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "totallyinvalidtoken", "password": "Password123"},
        )
        assert resp.status_code == 400

    async def test_expired_token_returns_400(self, client, db_session):
        from datetime import datetime, timedelta, timezone

        user = await create_user(db_session)
        raw = generate_raw_token()
        expired_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db_session.add(expired_token)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "Password123"},
        )
        assert resp.status_code == 400

    async def test_password_too_short_returns_422(self, client, db_session):
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "anytoken", "password": "short"},
        )
        assert resp.status_code == 422
