"""Tests für _recheck_new_partner_reviews: nur treffende Zeilen dürfen verschoben werden."""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import JournalLine, utcnow
from app.services.models import Service, ServiceMatcher
from app.services.service import ensure_base_service
from tests.journal import (
    assign_user_to_mandant,
    create_account_db,
    create_import_run_db,
    create_journal_line_db,
    create_mandant,
    create_partner_db,
    create_user,
    get_auth_token,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_non_base_service(
    session: AsyncSession,
    partner_id,
    name: str = "Lizenzen",
) -> Service:
    now = utcnow()
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type="supplier",
        tax_rate=Decimal("20.00"),
        service_type_manual=True,
        tax_rate_manual=True,
        created_at=now,
        updated_at=now,
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


@pytest.mark.asyncio
class TestMatcherRecheckOnlyMovesMatchingLines:
    """Beim Anlegen eines Matchers dürfen NUR die treffenden Zeilen verschoben werden."""

    async def test_only_matching_lines_are_moved(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Gegeben: Partner A mit 2 Zeilen (eine trifft den neuen Matcher, eine nicht).
        Wenn ein Matcher bei Partner B angelegt wird, der auf Zeile 1 von A passt,
        dann: nur Zeile 1 wechselt zu B, Zeile 2 bleibt bei A.
        """
        user = await create_user(db_session, "test@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        token = await get_auth_token(client, user, mandant)

        partner_a = await create_partner_db(db_session, mandant.id, "Partner A")
        partner_b = await create_partner_db(db_session, mandant.id, "Partner B")

        # Zeile 1 trifft den Matcher (enthält "INVOICE-42")
        line_matching = await create_journal_line_db(
            db_session, account.id, run.id,
            partner_id=partner_a.id,
            partner_name_raw="Partner A",
        )
        now = utcnow()
        line_matching.text = "INVOICE-42 Bezahlung"
        db_session.add(line_matching)

        # Zeile 2 trifft den Matcher NICHT
        line_non_matching = await create_journal_line_db(
            db_session, account.id, run.id,
            partner_id=partner_a.id,
            partner_name_raw="Partner A",
        )
        line_non_matching.text = "Monatsgebühr"
        db_session.add(line_non_matching)

        await db_session.commit()

        # Partner B: Basisleistung + eigene Leistung vorbereiten
        await ensure_base_service(db_session, partner_b.id)
        service_b = await _create_non_base_service(db_session, partner_b.id, "Rechnungen")

        # Matcher bei Partner B anlegen → löst _recheck_new_partner_reviews aus
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_b.id}/matchers",
            json={"pattern": "INVOICE-42", "pattern_type": "string"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

        # Zeile 1 muss jetzt bei Partner B sein
        await db_session.refresh(line_matching)
        assert line_matching.partner_id == partner_b.id, (
            "Die treffende Zeile muss zu Partner B verschoben worden sein"
        )

        # Zeile 2 muss WEITERHIN bei Partner A sein
        await db_session.refresh(line_non_matching)
        assert line_non_matching.partner_id == partner_a.id, (
            "Die nicht-treffende Zeile darf NICHT verschoben werden"
        )

    async def test_source_partner_deleted_only_when_all_lines_moved(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Wenn alle Zeilen von A verschoben werden, wird A gelöscht.
        Wenn nur manche Zeilen verschoben werden, bleibt A erhalten.
        """
        user = await create_user(db_session, "test2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        token = await get_auth_token(client, user, mandant)

        partner_a = await create_partner_db(db_session, mandant.id, "Partner A bleibend")
        partner_b = await create_partner_db(db_session, mandant.id, "Partner B")

        # Zwei Zeilen bei A: nur eine trifft
        line_matching = await create_journal_line_db(
            db_session, account.id, run.id, partner_id=partner_a.id
        )
        line_matching.text = "KEEPME Zahlung"
        db_session.add(line_matching)

        line_staying = await create_journal_line_db(
            db_session, account.id, run.id, partner_id=partner_a.id
        )
        line_staying.text = "Andere Buchung"
        db_session.add(line_staying)

        await db_session.commit()

        await ensure_base_service(db_session, partner_b.id)
        service_b = await _create_non_base_service(db_session, partner_b.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_b.id}/matchers",
            json={"pattern": "KEEPME", "pattern_type": "string"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

        # Partner A darf NICHT gelöscht worden sein (hat noch Zeile 2)
        from app.partners.models import Partner
        remaining_a = await db_session.get(Partner, partner_a.id)
        assert remaining_a is not None, "Partner A darf nicht gelöscht werden, hat noch Zeilen"

    async def test_source_partner_deleted_when_all_lines_match(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Wenn alle Zeilen von A verschoben werden (alle treffen), wird A gelöscht.
        """
        user = await create_user(db_session, "test3@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        token = await get_auth_token(client, user, mandant)

        partner_a = await create_partner_db(db_session, mandant.id, "Partner A wird gelöscht")
        partner_b = await create_partner_db(db_session, mandant.id, "Partner B")

        # Beide Zeilen bei A treffen den Matcher
        for i in range(2):
            line = await create_journal_line_db(
                db_session, account.id, run.id, partner_id=partner_a.id
            )
            line.text = f"MOVEALL Rechnung {i}"
            db_session.add(line)
        await db_session.commit()

        await ensure_base_service(db_session, partner_b.id)
        service_b = await _create_non_base_service(db_session, partner_b.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_b.id}/matchers",
            json={"pattern": "MOVEALL", "pattern_type": "string"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

        from app.partners.models import Partner
        deleted_a = await db_session.get(Partner, partner_a.id)
        assert deleted_a is None, "Partner A muss gelöscht worden sein, da alle Zeilen verschoben wurden"
