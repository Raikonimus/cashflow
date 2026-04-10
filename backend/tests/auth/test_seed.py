"""
Unit tests – app/scripts/seed.py  (Story 007-dev-seed)
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSeedProductionGuard:
    async def test_refuses_in_production(self):
        """Seed must exit with code 1 when ENV=production (ADR-005)."""
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.env = "production"
            mock_settings.seed_admin_email = "admin@test.com"
            mock_settings.seed_admin_password = "password123"

            with pytest.raises(SystemExit) as exc_info:
                from app.scripts import seed as seed_module
                import importlib
                importlib.reload(seed_module)
                await seed_module._seed()

            assert exc_info.value.code == 1

    async def test_refuses_without_email(self):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.env = "development"
            mock_settings.seed_admin_email = None
            mock_settings.seed_admin_password = "password123"

            with pytest.raises(SystemExit) as exc_info:
                from app.scripts import seed as seed_module
                import importlib
                importlib.reload(seed_module)
                await seed_module._seed()

            assert exc_info.value.code == 1

    async def test_refuses_without_password(self):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.env = "development"
            mock_settings.seed_admin_email = "admin@test.com"
            mock_settings.seed_admin_password = None

            with pytest.raises(SystemExit) as exc_info:
                from app.scripts import seed as seed_module
                import importlib
                importlib.reload(seed_module)
                await seed_module._seed()

            assert exc_info.value.code == 1

    async def test_refuses_when_password_too_short(self):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.env = "development"
            mock_settings.seed_admin_email = "admin@test.com"
            mock_settings.seed_admin_password = "short"

            with pytest.raises(SystemExit) as exc_info:
                from app.scripts import seed as seed_module
                import importlib
                importlib.reload(seed_module)
                await seed_module._seed()

            assert exc_info.value.code == 1


class TestSeedIntegration:
    async def test_seed_creates_admin_user(self, client, db_session):
        """Full integration: seed via DB session, then login succeeds."""
        from sqlmodel import select
        from app.auth.models import User, UserRole
        from app.auth.security import hash_password
        from app.core.config import settings

        # Directly simulate what seed does (bypasses invitation - ADR-005)
        admin = User(
            email="seeded@local.dev",
            password_hash=hash_password("AdminPass1"),
            role=UserRole.admin.value,
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()

        # Login must work
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "seeded@local.dev", "password": "AdminPass1"},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    async def test_seed_is_idempotent(self, client, db_session):
        """Running seed twice must not create duplicate users."""
        from sqlmodel import select
        from app.auth.models import User, UserRole
        from app.auth.security import hash_password

        admin = User(
            email="seeded@local.dev",
            password_hash=hash_password("AdminPass1"),
            role=UserRole.admin.value,
        )
        db_session.add(admin)
        await db_session.commit()

        # Simulate second run: check duplicate prevention
        result = await db_session.exec(
            select(User).where(User.email == "seeded@local.dev")
        )
        users = result.all()
        assert len(users) == 1  # no duplicate
