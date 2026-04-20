"""Shared fixtures for journal & audit tests."""
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import MandantUser, User, UserRole
from app.auth.security import hash_password
from app.imports.models import ImportRun, ImportStatus, JournalLine
from app.main import app
from app.partners.models import Partner
from app.tenants.models import Account, Mandant

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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    now = utcnow()
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
        intermediate_token = data["access_token"]
        resp2 = await client.post(
            "/api/v1/auth/select-mandant",
            json={"mandant_id": str(mandant.id)},
            headers={"Authorization": f"Bearer {intermediate_token}"},
        )
        return resp2.json()["access_token"]
    return data["access_token"]


async def create_account_db(
    session: AsyncSession,
    mandant_id: UUID,
    name: str = "Hauptkonto",
) -> Account:
    now = utcnow()
    account = Account(mandant_id=mandant_id, name=name, created_at=now, updated_at=now)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def create_import_run_db(
    session: AsyncSession,
    account_id: UUID,
    mandant_id: UUID,
    user_id: UUID,
) -> ImportRun:
    run = ImportRun(
        account_id=account_id,
        mandant_id=mandant_id,
        user_id=user_id,
        filename="test.csv",
        row_count=0,
        status=ImportStatus.completed.value,
        created_at=utcnow(),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def create_journal_line_db(
    session: AsyncSession,
    account_id: UUID,
    import_run_id: UUID,
    *,
    partner_id: UUID | None = None,
    valuta_date: str = "2025-01-15",
    amount: Decimal = Decimal("100.00"),
    partner_name_raw: str | None = "Lieferant GmbH",
) -> JournalLine:
    line = JournalLine(
        account_id=account_id,
        import_run_id=import_run_id,
        partner_id=partner_id,
        valuta_date=valuta_date,
        booking_date=valuta_date,
        amount=amount,
        currency="EUR",
        text="Rechnung",
        partner_name_raw=partner_name_raw,
        created_at=utcnow(),
    )
    session.add(line)
    await session.commit()
    await session.refresh(line)
    return line


async def create_partner_db(
    session: AsyncSession,
    mandant_id: UUID,
    name: str = "Lieferant GmbH",
) -> Partner:
    now = utcnow()
    partner = Partner(mandant_id=mandant_id, name=name, created_at=now, updated_at=now)
    session.add(partner)
    await session.commit()
    await session.refresh(partner)
    return partner
