"""Tests für den Kontosalden-Report (Liquiditätsprognose Phase 0)."""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserRole
from tests.journal import (
    assign_user_to_mandant,
    create_account_db,
    create_import_run_db,
    create_journal_line_db,
    create_mandant,
    create_user,
    get_auth_token,
)

BALANCES_URL = "/api/v1/mandants/{mandant_id}/reports/account-balances"


async def _setup(
    db_session: AsyncSession, client: AsyncClient, role: UserRole = UserRole.accountant
):
    user = await create_user(db_session, "acc@test.com", role)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    token = await get_auth_token(client, user, mandant)
    return user, mandant, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestAccountBalances:
    async def test_balance_is_opening_balance_plus_bookings(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user, mandant, headers = await _setup(db_session, client)
        account = await create_account_db(
            db_session, mandant.id, "Girokonto", opening_balance=Decimal("1500.00")
        )
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        await create_journal_line_db(
            db_session,
            account.id,
            run.id,
            amount=Decimal("250.00"),
            valuta_date="2025-03-01",
        )
        await create_journal_line_db(
            db_session,
            account.id,
            run.id,
            amount=Decimal("-100.50"),
            valuta_date="2025-04-15",
        )

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        assert resp.status_code == 200
        row = resp.json()["accounts"][0]
        assert row["account_name"] == "Girokonto"
        assert row["opening_balance"] == "1500.00"
        assert row["booked_amount"] == "149.50"
        assert row["current_balance"] == "1649.50"
        assert row["line_count"] == 2
        assert row["last_booking_date"] == "2025-04-15"

    async def test_account_without_bookings_returns_opening_balance(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, mandant, headers = await _setup(db_session, client)
        await create_account_db(
            db_session, mandant.id, "Leer", opening_balance=Decimal("42.00")
        )

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        row = resp.json()["accounts"][0]
        assert row["booked_amount"] == "0.00"
        assert row["current_balance"] == "42.00"
        assert row["line_count"] == 0
        assert row["last_booking_date"] is None

    async def test_default_opening_balance_is_zero(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user, mandant, headers = await _setup(db_session, client)
        account = await create_account_db(db_session, mandant.id, "Ohne Startsaldo")
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        await create_journal_line_db(
            db_session, account.id, run.id, amount=Decimal("80.00")
        )

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        row = resp.json()["accounts"][0]
        assert row["opening_balance"] == "0.00"
        assert row["current_balance"] == "80.00"

    async def test_foreign_currency_lines_are_counted_not_added(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user, mandant, headers = await _setup(db_session, client)
        account = await create_account_db(db_session, mandant.id, "EUR-Konto")
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        await create_journal_line_db(
            db_session, account.id, run.id, amount=Decimal("100.00")
        )
        await create_journal_line_db(
            db_session, account.id, run.id, amount=Decimal("999.00"), currency="USD"
        )

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        row = resp.json()["accounts"][0]
        assert row["current_balance"] == "100.00"
        assert row["line_count"] == 1
        assert row["foreign_currency_line_count"] == 1

    async def test_totals_are_grouped_per_currency(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user, mandant, headers = await _setup(db_session, client)
        eur = await create_account_db(
            db_session, mandant.id, "A EUR", opening_balance=Decimal("100.00")
        )
        await create_account_db(
            db_session, mandant.id, "B EUR", opening_balance=Decimal("200.00")
        )
        await create_account_db(
            db_session,
            mandant.id,
            "C USD",
            currency="USD",
            opening_balance=Decimal("50.00"),
        )
        run = await create_import_run_db(db_session, eur.id, mandant.id, user.id)
        await create_journal_line_db(
            db_session, eur.id, run.id, amount=Decimal("25.00")
        )

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        totals = {total["currency"]: total for total in resp.json()["totals"]}
        assert totals["EUR"]["account_count"] == 2
        assert totals["EUR"]["opening_balance"] == "300.00"
        assert totals["EUR"]["current_balance"] == "325.00"
        assert totals["USD"]["account_count"] == 1
        assert totals["USD"]["current_balance"] == "50.00"

    async def test_other_mandant_accounts_are_excluded(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, mandant, headers = await _setup(db_session, client)
        other = await create_mandant(db_session, "Fremd GmbH")
        await create_account_db(db_session, mandant.id, "Eigenes")
        await create_account_db(db_session, other.id, "Fremdes")

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        names = [row["account_name"] for row in resp.json()["accounts"]]
        assert names == ["Eigenes"]

    async def test_viewer_may_read_balances(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, mandant, headers = await _setup(db_session, client, role=UserRole.viewer)
        await create_account_db(db_session, mandant.id, "Girokonto")

        resp = await client.get(
            BALANCES_URL.format(mandant_id=mandant.id), headers=headers
        )

        assert resp.status_code == 200

    async def test_requires_authentication(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        mandant = await create_mandant(db_session)

        resp = await client.get(BALANCES_URL.format(mandant_id=mandant.id))

        assert resp.status_code == 401
