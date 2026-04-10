from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserRole
from app.imports.models import utcnow
from app.services.models import Service
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


async def _create_service(
    session: AsyncSession,
    partner_id,
    name: str,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> Service:
    now = utcnow()
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type="unknown",
        tax_rate=Decimal("20.00"),
        valid_from=valid_from,
        valid_to=valid_to,
        created_at=now,
        updated_at=now,
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


@pytest.mark.asyncio
class TestManualServiceAssignment:
    async def test_assign_service_sets_manual_mode(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "journal-svc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id)
        line = await create_journal_line_db(db_session, account.id, run.id, partner_id=partner.id)
        token = await get_auth_token(client, user, mandant)

        await ensure_base_service(db_session, partner.id)
        service = await _create_service(db_session, partner.id, "Beratung")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/{line.id}/assign-service",
            json={"service_id": str(service.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["service_id"] == str(service.id)
        assert payload["service_assignment_mode"] == "manual"

        await db_session.refresh(line)
        assert line.service_id == service.id
        assert line.service_assignment_mode == "manual"

    async def test_assign_service_rejects_service_from_other_partner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "journal-wrong@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id, "Partner A")
        other_partner = await create_partner_db(db_session, mandant.id, "Partner B")
        line = await create_journal_line_db(db_session, account.id, run.id, partner_id=partner.id)
        token = await get_auth_token(client, user, mandant)

        await ensure_base_service(db_session, partner.id)
        await ensure_base_service(db_session, other_partner.id)
        other_service = await _create_service(db_session, other_partner.id, "Fremdleistung")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/{line.id}/assign-service",
            json={"service_id": str(other_service.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_assign_service_rejects_outside_validity_window(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "journal-date@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id)
        line = await create_journal_line_db(db_session, account.id, run.id, partner_id=partner.id, valuta_date="2025-01-15")
        token = await get_auth_token(client, user, mandant)

        await ensure_base_service(db_session, partner.id)
        service = await _create_service(db_session, partner.id, "Zeitlich begrenzt", valid_from=date(2026, 1, 1))

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/{line.id}/assign-service",
            json={"service_id": str(service.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 422