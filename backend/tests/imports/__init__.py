"""Shared fixtures for partner merge and import tests."""
# pylint: disable=redefined-outer-name
import io
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import MandantUser, User, UserRole
from app.auth.security import hash_password
from app.main import app
from app.partners.models import Partner, PartnerIban, PartnerName
from app.tenants.models import Account, ColumnMappingConfig, Mandant

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


async def get_auth_token(http_client: AsyncClient, user: User, mandant: Mandant) -> str:
    resp = await http_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "password123"},
    )
    data = resp.json()
    if data.get("requires_mandant_selection"):
        intermediate_token = data["access_token"]
        resp2 = await http_client.post(
            "/api/v1/auth/select-mandant",
            json={"mandant_id": str(mandant.id)},
            headers={"Authorization": f"Bearer {intermediate_token}"},
        )
        return resp2.json()["access_token"]
    return data["access_token"]


async def create_partner_db(
    session: AsyncSession,
    mandant_id: UUID,
    name: str = "Test Partner",
    iban: str | None = None,
) -> Partner:
    now = utcnow()
    partner = Partner(mandant_id=mandant_id, name=name, created_at=now, updated_at=now)
    session.add(partner)
    await session.flush()
    if iban:
        pi = PartnerIban(partner_id=partner.id, iban=iban, created_at=now)
        session.add(pi)
    await session.commit()
    await session.refresh(partner)
    return partner


async def create_account_db(
    session: AsyncSession,
    mandant_id: UUID,
    name: str = "Girokonto",
) -> Account:
    now = utcnow()
    account = Account(mandant_id=mandant_id, name=name, created_at=now, updated_at=now)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def create_mapping_db(
    session: AsyncSession,
    account_id: UUID,
    valuta_col: str = "Valuta",
    booking_col: str = "Buchungsdatum",
    amount_col: str = "Betrag",
    partner_name_col: str | None = "Auftraggeber",
    partner_iban_col: str | None = "IBAN",
    description_col: str | None = None,
    date_format: str = "%Y-%m-%d",
    decimal_separator: str = ".",
    delimiter: str = ",",
) -> ColumnMappingConfig:
    now = utcnow()
    mapping = ColumnMappingConfig(
        account_id=account_id,
        valuta_date_col=valuta_col,
        booking_date_col=booking_col,
        amount_col=amount_col,
        partner_name_col=partner_name_col,
        partner_iban_col=partner_iban_col,
        description_col=description_col,
        decimal_separator=decimal_separator,
        date_format=date_format,
        delimiter=delimiter,
        encoding="utf-8",
        skip_rows=0,
        created_at=now,
        updated_at=now,
    )
    session.add(mapping)
    await session.commit()
    await session.refresh(mapping)
    return mapping


def make_csv(rows: list[dict], delimiter: str = ",") -> bytes:
    """Build a CSV file from a list of dicts."""
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


import csv  # noqa: E402 (needs to be after imports for Python 3.13 compatibility)
