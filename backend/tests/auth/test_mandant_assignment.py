"""
Integration tests – Mandant assignment
POST /api/v1/mandants/:id/users
DELETE /api/v1/mandants/:id/users/:uid
(Story 004-mandant-user-assignment)
"""
import pytest

from tests.auth.conftest import assign_user_to_mandant, create_mandant, create_user
from app.auth.models import UserRole


async def _admin_token(client, db_session) -> str:
    await create_user(db_session, email="admin@test.com", role=UserRole.admin)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "admin@test.com", "password": "secret123"}
    )
    return resp.json()["access_token"]


class TestMandantAssignment:
    async def test_admin_can_assign_user_to_mandant(self, client, db_session):
        adm_token = await _admin_token(client, db_session)
        user = await create_user(db_session, email="user@test.com", role=UserRole.viewer)
        mandant = await create_mandant(db_session)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/users",
            json={"user_id": str(user.id)},
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert str(data["user_id"]) == str(user.id)
        assert str(data["mandant_id"]) == str(mandant.id)

    async def test_duplicate_assignment_returns_409(self, client, db_session):
        adm_token = await _admin_token(client, db_session)
        user = await create_user(db_session, email="user@test.com", role=UserRole.viewer)
        mandant = await create_mandant(db_session)

        await client.post(
            f"/api/v1/mandants/{mandant.id}/users",
            json={"user_id": str(user.id)},
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/users",
            json={"user_id": str(user.id)},
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 409

    async def test_assign_unknown_user_returns_404(self, client, db_session):
        from uuid import uuid4
        adm_token = await _admin_token(client, db_session)
        mandant = await create_mandant(db_session)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/users",
            json={"user_id": str(uuid4())},
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 404

    async def test_assign_unknown_mandant_returns_404(self, client, db_session):
        from uuid import uuid4
        adm_token = await _admin_token(client, db_session)
        user = await create_user(db_session, email="user@test.com", role=UserRole.viewer)

        resp = await client.post(
            f"/api/v1/mandants/{uuid4()}/users",
            json={"user_id": str(user.id)},
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 404

    async def test_admin_can_unassign_user(self, client, db_session):
        adm_token = await _admin_token(client, db_session)
        user = await create_user(db_session, email="user@test.com", role=UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)

        resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/users/{user.id}",
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 204

    async def test_unassign_non_existing_returns_404(self, client, db_session):
        from uuid import uuid4
        adm_token = await _admin_token(client, db_session)
        mandant = await create_mandant(db_session)
        user = await create_user(db_session, email="user@test.com", role=UserRole.viewer)

        resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/users/{user.id}",
            headers={"Authorization": f"Bearer {adm_token}"},
        )
        assert resp.status_code == 404

    async def test_non_admin_cannot_assign(self, client, db_session):
        ma = await create_user(db_session, email="ma@test.com", role=UserRole.mandant_admin)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, ma, mandant)
        user = await create_user(db_session, email="user@test.com", role=UserRole.viewer)

        resp_login = await client.post(
            "/api/v1/auth/login", json={"email": "ma@test.com", "password": "secret123"}
        )
        token = resp_login.json()["access_token"]

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/users",
            json={"user_id": str(user.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_assigned_user_can_select_mandant(self, client, db_session):
        """After assignment, user should be able to select the mandant."""
        adm_token = await _admin_token(client, db_session)
        user = await create_user(db_session, email="user@test.com", role=UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@test.com", "password": "secret123"},
        )
        user_token = login.json()["access_token"]

        resp = await client.post(
            "/api/v1/auth/select-mandant",
            json={"mandant_id": str(mandant.id)},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
