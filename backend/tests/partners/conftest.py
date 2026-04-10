"""Shared fixtures for partner tests (mirrors tenants/conftest.py)."""
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import MandantUser, User, UserRole
from app.auth.security import hash_password
from app.main import app
from app.tenants.models import Mandant

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


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


async def create_user(
    session: AsyncSession,
    email: str = "user@example.com",
    role: UserRole = UserRole.accountant,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        role=role.value,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_mandant(session: AsyncSession, name: str = "Test GmbH") -> Mandant:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    mandant = Mandant(name=name, created_at=now, updated_at=now)
    session.add(mandant)
    await session.commit()
    await session.refresh(mandant)
    return mandant


async def assign_user_to_mandant(
    session: AsyncSession, user: User, mandant: Mandant
) -> MandantUser:
    mu = MandantUser(mandant_id=mandant.id, user_id=user.id)
    session.add(mu)
    await session.commit()
    return mu


async def get_auth_token(client: AsyncClient, user: User, mandant: Mandant) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "password123"},
    )
    data = resp.json()
    if data.get("requires_mandant_selection"):
        resp2 = await client.post(
            "/api/v1/auth/select-mandant", json={"mandant_id": str(mandant.id)}
        )
        return resp2.json()["access_token"]
    return data["access_token"]
