"""
Integration tests – RBAC middleware / dependencies  (Story 005-rbac-middleware)
"""
import pytest
from fastapi import Depends
from fastapi.routing import APIRouter

from tests.auth.conftest import assign_user_to_mandant, create_mandant, create_user
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import User, UserRole
from app.auth.security import create_access_token
from app.main import app


# ──────────────────────────────────────────────────────────────────────────────
# Register test-only endpoints to check role guards
# ──────────────────────────────────────────────────────────────────────────────
_test_router = APIRouter(prefix="/test-rbac", tags=["test"])


@_test_router.get("/accountant-only")
async def accountant_only(u: User = Depends(require_role("accountant"))):
    return {"ok": True}


@_test_router.get("/mandant-admin-only")
async def mandant_admin_only(u: User = Depends(require_role("mandant_admin"))):
    return {"ok": True}


@_test_router.get("/admin-only")
async def admin_only(u: User = Depends(require_role("admin"))):
    return {"ok": True}


app.include_router(_test_router, prefix="/api/v1")


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────


async def _login_token(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return resp.json()["access_token"]


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestMissingToken:
    async def test_protected_endpoint_without_token_returns_401(self, client, db_session):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client, db_session):
        resp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer notavalidtoken"}
        )
        assert resp.status_code == 401


class TestRoleHierarchy:
    async def test_viewer_cannot_access_accountant_endpoint(self, client, db_session):
        await create_user(db_session, role=UserRole.viewer)
        token = await _login_token(client, "test@example.com", "secret123")
        resp = await client.get(
            "/api/v1/test-rbac/accountant-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_accountant_can_access_accountant_endpoint(self, client, db_session):
        await create_user(db_session, role=UserRole.accountant)
        token = await _login_token(client, "test@example.com", "secret123")
        resp = await client.get(
            "/api/v1/test-rbac/accountant-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_accountant_cannot_access_mandant_admin_endpoint(self, client, db_session):
        await create_user(db_session, role=UserRole.accountant)
        token = await _login_token(client, "test@example.com", "secret123")
        resp = await client.get(
            "/api/v1/test-rbac/mandant-admin-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_mandant_admin_can_access_accountant_endpoint(self, client, db_session):
        await create_user(db_session, role=UserRole.mandant_admin)
        token = await _login_token(client, "test@example.com", "secret123")
        resp = await client.get(
            "/api/v1/test-rbac/accountant-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_admin_can_access_all_endpoints(self, client, db_session):
        await create_user(db_session, role=UserRole.admin)
        token = await _login_token(client, "test@example.com", "secret123")

        for path in ["/accountant-only", "/mandant-admin-only", "/admin-only"]:
            resp = await client.get(
                f"/api/v1/test-rbac{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, f"Failed for {path}: {resp.json()}"


class TestInactiveUserBlocked:
    async def test_inactive_user_token_rejected(self, client, db_session):
        """Simulate a token for a now-deactivated user."""
        user = await create_user(db_session, role=UserRole.accountant, is_active=False)
        # Craft a valid JWT for the inactive user directly
        token = create_access_token(
            {"sub": str(user.id), "role": user.role, "mandant_id": None}
        )
        resp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401
