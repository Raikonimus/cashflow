from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import JournalLine
from app.services.models import Service, utcnow
from tests.testing.conftest import (
    assign_user_to_mandant,
    create_account_db,
    create_import_run_db,
    create_journal_line_db,
    create_mandant,
    create_partner_db,
    create_user,
    get_auth_token,
)


@pytest.mark.asyncio
async def test_service_amount_consistency_lists_services_with_mixed_signs(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, "testing@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    run = await create_import_run_db(db_session, account.id, mandant.id, user.id)

    partner_a = await create_partner_db(db_session, mandant.id, "Alpha GmbH")
    partner_b = await create_partner_db(db_session, mandant.id, "Beta GmbH")

    mixed_service = Service(
        partner_id=partner_a.id,
        name="Hosting",
        service_type="supplier",
        tax_rate="20.00",
        erfolgsneutral=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    one_sided_service = Service(
        partner_id=partner_b.id,
        name="Lizenz",
        service_type="customer",
        tax_rate="20.00",
        erfolgsneutral=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(mixed_service)
    db_session.add(one_sided_service)
    await db_session.commit()
    await db_session.refresh(mixed_service)
    await db_session.refresh(one_sided_service)

    negative_line = await create_journal_line_db(
        db_session,
        account.id,
        run.id,
        partner_id=partner_a.id,
        valuta_date="2026-02-01",
        amount=Decimal("-50.00"),
        partner_name_raw="Alpha GmbH",
    )
    positive_line = await create_journal_line_db(
        db_session,
        account.id,
        run.id,
        partner_id=partner_a.id,
        valuta_date="2026-02-02",
        amount=Decimal("25.00"),
        partner_name_raw="Alpha GmbH",
    )
    only_negative_line = await create_journal_line_db(
        db_session,
        account.id,
        run.id,
        partner_id=partner_b.id,
        valuta_date="2026-02-03",
        amount=Decimal("-10.00"),
        partner_name_raw="Beta GmbH",
    )

    negative_line.service_id = mixed_service.id
    positive_line.service_id = mixed_service.id
    only_negative_line.service_id = one_sided_service.id
    db_session.add(negative_line)
    db_session.add(positive_line)
    db_session.add(only_negative_line)
    await db_session.commit()

    token = await get_auth_token(client, user, mandant)
    response = await client.post(
        f"/api/v1/mandants/{mandant.id}/settings/tests/service-amount-consistency",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_checked_services"] == 2
    assert len(payload["inconsistent_services"]) == 1

    inconsistent_service = payload["inconsistent_services"][0]
    assert inconsistent_service["service_name"] == "Hosting"
    assert inconsistent_service["partner_name"] == "Alpha GmbH"
    assert inconsistent_service["positive_line_count"] == 1
    assert inconsistent_service["negative_line_count"] == 1
    assert all(line["service_amount_consistency_ok"] is False for line in inconsistent_service["lines"])
    assert {line["id"] for line in inconsistent_service["lines"]} == {
        str(negative_line.id),
        str(positive_line.id),
    }


@pytest.mark.asyncio
async def test_service_amount_consistency_ignores_marked_lines_for_detection(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, "testing-ok@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    run = await create_import_run_db(db_session, account.id, mandant.id, user.id)

    partner = await create_partner_db(db_session, mandant.id, "Alpha GmbH")
    mixed_service = Service(
        partner_id=partner.id,
        name="Hosting",
        service_type="supplier",
        tax_rate="20.00",
        erfolgsneutral=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(mixed_service)
    await db_session.commit()
    await db_session.refresh(mixed_service)

    negative_line = await create_journal_line_db(
        db_session,
        account.id,
        run.id,
        partner_id=partner.id,
        valuta_date="2026-02-01",
        amount=Decimal("-50.00"),
        partner_name_raw="Alpha GmbH",
    )
    ignored_positive_line = await create_journal_line_db(
        db_session,
        account.id,
        run.id,
        partner_id=partner.id,
        valuta_date="2026-02-02",
        amount=Decimal("25.00"),
        partner_name_raw="Alpha GmbH",
        service_amount_consistency_ok=True,
    )

    negative_line.service_id = mixed_service.id
    ignored_positive_line.service_id = mixed_service.id
    db_session.add(negative_line)
    db_session.add(ignored_positive_line)
    await db_session.commit()

    token = await get_auth_token(client, user, mandant)
    response = await client.post(
        f"/api/v1/mandants/{mandant.id}/settings/tests/service-amount-consistency",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_checked_services"] == 1
    assert payload["inconsistent_services"] == []


@pytest.mark.asyncio
async def test_service_amount_consistency_ok_can_be_toggled_per_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, "toggle-ok@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
    partner = await create_partner_db(db_session, mandant.id, "Alpha GmbH")

    line = await create_journal_line_db(
        db_session,
        account.id,
        run.id,
        partner_id=partner.id,
        amount=Decimal("25.00"),
        partner_name_raw="Alpha GmbH",
    )

    token = await get_auth_token(client, user, mandant)
    response = await client.post(
        f"/api/v1/mandants/{mandant.id}/settings/tests/service-amount-consistency/lines/{line.id}/ok",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_ok": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "journal_line_id": str(line.id),
        "service_amount_consistency_ok": True,
    }

    refreshed_line = (
        await db_session.exec(select(JournalLine).where(JournalLine.id == line.id))
    ).one()
    assert refreshed_line.service_amount_consistency_ok is True