"""
Shared fixtures for all auth tests.
"""
import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.auth.models import Mandant, MandantUser, User, UserRole
from app.auth.security import hash_password
from app.core.config import settings
from app.main import app

# Use an in-memory SQLite DB for tests (no external infra needed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True, scope="function")
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.core.database import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_user(
    session: AsyncSession,
    email: str = "test@example.com",
    password: str = "secret123",
    role: UserRole = UserRole.accountant,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password) if password else None,
        role=role.value,
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_mandant(session: AsyncSession, name: str = "Test GmbH") -> Mandant:
    mandant = Mandant(name=name)
    session.add(mandant)
    await session.commit()
    await session.refresh(mandant)
    return mandant


async def assign_user_to_mandant(
    session: AsyncSession, user: User, mandant: Mandant
) -> None:
    session.add(MandantUser(user_id=user.id, mandant_id=mandant.id))
    await session.commit()
