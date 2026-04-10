"""
Integration tests – POST /api/v1/auth/login  (Story 001-login-jwt)
"""
import pytest

from tests.auth.conftest import assign_user_to_mandant, create_mandant, create_user
from app.auth.models import UserRole


class TestLoginSuccess:
    async def test_admin_login_no_mandant(self, client, db_session):
        await create_user(db_session, role=UserRole.admin)
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert data["requires_mandant_selection"] is False

    async def test_single_mandant_embedded_in_token(self, client, db_session):
        user = await create_user(db_session)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)

        resp = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_mandant_selection"] is False
        assert data["mandants"][0]["name"] == "Test GmbH"

        # mandant_id must be embedded in JWT
        from app.auth.security import decode_access_token
        payload = decode_access_token(data["access_token"])
        assert payload["mandant_id"] == str(mandant.id)

    async def test_multiple_mandants_requires_selection(self, client, db_session):
        user = await create_user(db_session)
        m1 = await create_mandant(db_session, "Firma A")
        m2 = await create_mandant(db_session, "Firma B")
        await assign_user_to_mandant(db_session, user, m1)
        await assign_user_to_mandant(db_session, user, m2)

        resp = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_mandant_selection"] is True
        assert len(data["mandants"]) == 2


class TestLoginFailures:
    async def test_wrong_password_returns_401(self, client, db_session):
        await create_user(db_session)
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "wrongpass"}
        )
        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]

    async def test_unknown_email_returns_401(self, client, db_session):
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "anypass"}
        )
        assert resp.status_code == 401

    async def test_inactive_user_returns_401(self, client, db_session):
        await create_user(db_session, is_active=False)
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        assert resp.status_code == 401

    async def test_pending_invitation_returns_401(self, client, db_session):
        """User without password_hash (invitation not yet accepted)."""
        await create_user(db_session, password=None)
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "anything"}
        )
        assert resp.status_code == 401
        assert "Invitation" in resp.json()["detail"]


class TestSelectMandant:
    async def test_select_valid_mandant(self, client, db_session):
        user = await create_user(db_session)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)

        login = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/v1/auth/select-mandant",
            json={"mandant_id": str(mandant.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    async def test_select_mandant_no_access_returns_403(self, client, db_session):
        user = await create_user(db_session)
        other_mandant = await create_mandant(db_session, "Other GmbH")

        login = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/v1/auth/select-mandant",
            json={"mandant_id": str(other_mandant.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


class TestGetMe:
    async def test_me_returns_user_info(self, client, db_session):
        user = await create_user(db_session, role=UserRole.accountant)
        login = await client.post(
            "/api/v1/auth/login", json={"email": "test@example.com", "password": "secret123"}
        )
        token = login.json()["access_token"]

        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert data["role"] == "accountant"

    async def test_me_without_token_returns_401(self, client, db_session):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
