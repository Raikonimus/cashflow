"""
Integration tests – POST /api/v1/users, GET /api/v1/users/:id, PATCH /api/v1/users/:id
(Story 003-user-crud)
"""
import pytest

from tests.auth.conftest import (
    assign_user_to_mandant,
    create_mandant,
    create_user,
)
from app.auth.models import UserRole


async def _login_token(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


class TestCreateUser:
    async def test_admin_can_create_any_role(self, client, db_session):
        await create_user(db_session, email="admin@test.com", role=UserRole.admin)
        token = await _login_token(client, "admin@test.com", "secret123")

        for role in ["accountant", "viewer", "mandant_admin"]:
            resp = await client.post(
                "/api/v1/users",
                json={"email": f"{role}@example.com", "role": role},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201, f"Failed for role={role}: {resp.json()}"
            data = resp.json()
            assert data["role"] == role
            assert data["invitation_status"] == "pending"

    async def test_mandant_admin_can_create_accountant_viewer(self, client, db_session):
        ma = await create_user(db_session, email="ma@test.com", role=UserRole.mandant_admin)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, ma, mandant)
        token = await _login_token(client, "ma@test.com", "secret123")

        for role in ["accountant", "viewer"]:
            resp = await client.post(
                "/api/v1/users",
                json={"email": f"{role}2@example.com", "role": role},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201, resp.json()

    async def test_mandant_admin_cannot_create_mandant_admin(self, client, db_session):
        ma = await create_user(db_session, email="ma@test.com", role=UserRole.mandant_admin)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, ma, mandant)
        token = await _login_token(client, "ma@test.com", "secret123")

        resp = await client.post(
            "/api/v1/users",
            json={"email": "newma@example.com", "role": "mandant_admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_mandant_admin_cannot_create_admin(self, client, db_session):
        ma = await create_user(db_session, email="ma@test.com", role=UserRole.mandant_admin)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, ma, mandant)
        token = await _login_token(client, "ma@test.com", "secret123")

        resp = await client.post(
            "/api/v1/users",
            json={"email": "newadmin@example.com", "role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_accountant_cannot_create_user(self, client, db_session):
        await create_user(db_session, role=UserRole.accountant)
        token = await _login_token(client, "test@example.com", "secret123")

        resp = await client.post(
            "/api/v1/users",
            json={"email": "new@example.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_duplicate_email_returns_400(self, client, db_session):
        await create_user(db_session, email="admin@test.com", role=UserRole.admin)
        token = await _login_token(client, "admin@test.com", "secret123")

        # Create once
        await client.post(
            "/api/v1/users",
            json={"email": "dup@example.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Create again
        resp = await client.post(
            "/api/v1/users",
            json={"email": "dup@example.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]


class TestGetUser:
    async def test_admin_can_get_any_user(self, client, db_session):
        admin = await create_user(db_session, email="admin@test.com", role=UserRole.admin)
        target = await create_user(db_session, email="target@test.com", role=UserRole.viewer)
        token = await _login_token(client, "admin@test.com", "secret123")

        resp = await client.get(
            f"/api/v1/users/{target.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "target@test.com"

    async def test_mandant_admin_cannot_get_user_from_other_mandant(self, client, db_session):
        ma = await create_user(db_session, email="ma@test.com", role=UserRole.mandant_admin)
        m1 = await create_mandant(db_session, "Mandant A")
        await assign_user_to_mandant(db_session, ma, m1)

        other_user = await create_user(db_session, email="other@test.com", role=UserRole.viewer)
        m2 = await create_mandant(db_session, "Mandant B")
        await assign_user_to_mandant(db_session, other_user, m2)

        token = await _login_token(client, "ma@test.com", "secret123")
        resp = await client.get(
            f"/api/v1/users/{other_user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


class TestUpdateUser:
    async def test_admin_can_deactivate_user(self, client, db_session):
        await create_user(db_session, email="admin@test.com", role=UserRole.admin)
        target = await create_user(db_session, email="target@test.com", role=UserRole.viewer)
        token = await _login_token(client, "admin@test.com", "secret123")

        resp = await client.patch(
            f"/api/v1/users/{target.id}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_deactivated_user_cannot_login(self, client, db_session):
        await create_user(db_session, email="admin@test.com", role=UserRole.admin)
        target = await create_user(db_session, email="target@test.com", role=UserRole.viewer)
        token = await _login_token(client, "admin@test.com", "secret123")

        await client.patch(
            f"/api/v1/users/{target.id}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "target@test.com", "password": "secret123"},
        )
        assert login_resp.status_code == 401
