"""Dublettenerkennung zaehlt Vorkommen statt Existenz zu pruefen.

Wiederholt importierte Dateien werden verworfen, mehrfach vorkommende echte
Buchungen innerhalb einer Datei aber uebernommen.
"""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import JournalLine
from app.tenants.models import ColumnMappingConfig
from tests.imports import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_account_db,
    create_mandant,
    create_user,
    db_session,
    get_auth_token,
    make_csv,
    setup_db,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _row(datum: str, betrag: str, zweck: str) -> dict:
    return {
        "Valuta": datum,
        "Buchungsdatum": datum,
        "Betrag": betrag,
        "Verwendungszweck": zweck,
    }


async def _setup(client: AsyncClient, db_session: AsyncSession, email: str):
    user = await create_user(db_session, email, UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    db_session.add(
        ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            description_col="Verwendungszweck",
            column_assignments=[
                {
                    "source": "Valuta",
                    "target": "valuta_date",
                    "sort_order": 0,
                    "duplicate_check": True,
                },
                {
                    "source": "Buchungsdatum",
                    "target": "booking_date",
                    "sort_order": 1,
                    "duplicate_check": False,
                },
                {
                    "source": "Betrag",
                    "target": "amount",
                    "sort_order": 2,
                    "duplicate_check": True,
                },
                {
                    "source": "Verwendungszweck",
                    "target": "description",
                    "sort_order": 3,
                    "duplicate_check": True,
                },
            ],
            decimal_separator=".",
            date_format="%Y-%m-%d",
            delimiter=",",
            encoding="utf-8",
            skip_rows=0,
        )
    )
    await db_session.commit()
    token = await get_auth_token(client, user, mandant)
    return mandant, account, token


async def _upload(
    client: AsyncClient, mandant, account, token, rows, name="auszug.csv"
) -> dict:
    resp = await client.post(
        f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
        files=[("files", (name, io.BytesIO(make_csv(rows)), "text/csv"))],
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()[0]


@pytest.mark.asyncio
class TestDuplicateCounting:
    async def test_gleiche_buchung_zweimal_in_einer_datei_wird_zweimal_importiert(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Zwei echte Zahlungen am selben Tag ueber denselben Betrag mit demselben
        Text sind nicht unterscheidbar - beide gehoeren trotzdem importiert."""
        mandant, account, token = await _setup(client, db_session, "dup1@test.com")

        run = await _upload(
            client,
            mandant,
            account,
            token,
            [
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
            ],
        )
        assert run["row_count"] == 2
        assert run["skipped_count"] == 0

        lines = (await db_session.exec(select(JournalLine))).all()
        assert len(lines) == 2

    async def test_dieselbe_datei_erneut_importiert_wird_vollstaendig_verworfen(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        mandant, account, token = await _setup(client, db_session, "dup2@test.com")
        rows = [
            _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
            _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
            _row("2026-01-16", "-19.17", "OPENAI"),
        ]
        first = await _upload(client, mandant, account, token, rows)
        assert first["row_count"] == 3

        second = await _upload(client, mandant, account, token, rows)
        assert second["row_count"] == 0
        assert second["skipped_count"] == 3

        lines = (await db_session.exec(select(JournalLine))).all()
        assert len(lines) == 3

    async def test_ueberlappender_export_importiert_nur_die_differenz(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Der zweite Export enthaelt dieselbe Buchung dreimal, gespeichert sind zwei -
        genau eine kommt dazu."""
        mandant, account, token = await _setup(client, db_session, "dup3@test.com")
        await _upload(
            client,
            mandant,
            account,
            token,
            [
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
            ],
        )

        run = await _upload(
            client,
            mandant,
            account,
            token,
            [
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
            ],
            name="nachtrag.csv",
        )
        assert run["row_count"] == 1
        assert run["skipped_count"] == 2

        lines = (await db_session.exec(select(JournalLine))).all()
        assert len(lines) == 3

    async def test_neue_buchungen_neben_bereits_bekannten(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        mandant, account, token = await _setup(client, db_session, "dup4@test.com")
        await _upload(
            client,
            mandant,
            account,
            token,
            [_row("2026-01-15", "-2.00", "CAR PARK DIRTL")],
        )

        run = await _upload(
            client,
            mandant,
            account,
            token,
            [
                _row("2026-01-15", "-2.00", "CAR PARK DIRTL"),
                _row("2026-01-16", "-19.17", "OPENAI"),
            ],
            name="februar.csv",
        )
        assert run["row_count"] == 1
        assert run["skipped_count"] == 1

        texts = sorted(
            (line.text or "")
            for line in (await db_session.exec(select(JournalLine))).all()
        )
        assert texts == ["CAR PARK DIRTL", "OPENAI"]

    async def test_verworfene_zeilen_werden_benannt(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        mandant, account, token = await _setup(client, db_session, "dup5@test.com")
        rows = [_row("2026-01-15", "-2.00", "CAR PARK DIRTL")]
        await _upload(client, mandant, account, token, rows)
        second = await _upload(client, mandant, account, token, rows)

        details = second["error_details"] or {}
        assert [d["text"] for d in details.get("duplicates", [])] == ["CAR PARK DIRTL"]
