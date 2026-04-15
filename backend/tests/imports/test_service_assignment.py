from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserRole
from app.imports.models import JournalLine, ReviewItem, utcnow
from app.services.models import Service, ServiceMatcher, ServiceMatcherType, ServiceType
from app.services.service import ensure_base_service
from tests.imports import (
    assign_user_to_mandant,
    create_account_db,
    create_mapping_db,
    create_mandant,
    create_partner_db,
    create_user,
    get_auth_token,
    make_csv,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_service(
    session: AsyncSession,
    partner_id,
    name: str,
    pattern: str | None = None,
    service_type: str = ServiceType.unknown.value,
) -> Service:
    now = utcnow()
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type=service_type,
        tax_rate=Decimal("20.00"),
        created_at=now,
        updated_at=now,
    )
    session.add(service)
    await session.flush()
    if pattern is not None:
        session.add(
            ServiceMatcher(
                service_id=service.id,
                pattern=pattern,
                pattern_type=ServiceMatcherType.string.value,
                created_at=now,
                updated_at=now,
            )
        )
    await session.commit()
    await session.refresh(service)
    return service


@pytest.mark.asyncio
class TestImportServiceAssignment:
    async def test_import_assigns_matching_service_automatically(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "svc-import@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id, description_col="Verwendungszweck")
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(
            db_session,
            mandant.id,
            name="Amazon EU",
            iban="DE89370400440532013000",
        )
        await ensure_base_service(db_session, partner.id)
        service = await _create_service(db_session, partner.id, "Hosting", pattern="hosting")

        csv_bytes = make_csv([
            {
                "Valuta": "2026-01-15",
                "Buchungsdatum": "2026-01-15",
                "Betrag": "123.45",
                "Auftraggeber": "Amazon EU",
                "IBAN": "DE89370400440532013000",
                "Verwendungszweck": "Hosting April",
            }
        ])
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", csv_bytes, "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201

        line = (await db_session.exec(select(JournalLine))).first()
        assert line is not None
        assert line.service_id == service.id
        assert line.service_assignment_mode == "auto"

    async def test_import_uses_base_service_and_creates_review_on_multiple_matches(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "svc-amb@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id, description_col="Verwendungszweck")
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(
            db_session,
            mandant.id,
            name="Amazon EU",
            iban="DE89370400440532013000",
        )
        base_service = await ensure_base_service(db_session, partner.id)
        await _create_service(db_session, partner.id, "Hosting", pattern="hosting")
        await _create_service(db_session, partner.id, "April Service", pattern="april")

        csv_bytes = make_csv([
            {
                "Valuta": "2026-01-15",
                "Buchungsdatum": "2026-01-15",
                "Betrag": "123.45",
                "Auftraggeber": "Amazon EU",
                "IBAN": "DE89370400440532013000",
                "Verwendungszweck": "Hosting April",
            }
        ])
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", csv_bytes, "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201

        line = (await db_session.exec(select(JournalLine))).first()
        assert line is not None
        assert line.service_id == base_service.id
        assert line.service_assignment_mode == "auto"

        review = (
            await db_session.exec(
                select(ReviewItem).where(ReviewItem.item_type == "service_assignment")
            )
        ).first()
        assert review is not None
        assert review.context["current_service_id"] == str(base_service.id)
        assert len(review.context["matching_services"]) == 2

    async def test_import_detects_service_type_and_creates_review(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "svc-type@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id, description_col="Verwendungszweck")
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(
            db_session,
            mandant.id,
            name="Payroll GmbH",
            iban="DE12500105170648489890",
        )
        await ensure_base_service(db_session, partner.id)
        service = await _create_service(db_session, partner.id, "Lohnlauf", pattern="lohn")

        csv_bytes = make_csv([
            {
                "Valuta": "2026-01-31",
                "Buchungsdatum": "2026-01-31",
                "Betrag": "-1500.00",
                "Auftraggeber": "Payroll GmbH",
                "IBAN": "DE12500105170648489890",
                "Verwendungszweck": "Lohn Januar",
            }
        ])
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", csv_bytes, "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201

        await db_session.refresh(service)
        assert service.service_type == ServiceType.employee.value
        assert service.tax_rate == Decimal("0.00")

        review = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_type_review",
                    ReviewItem.service_id == service.id,
                )
            )
        ).first()
        assert review is not None
        assert review.context["auto_assigned_type"] == ServiceType.employee.value

    async def test_import_detects_shareholder_service_type_from_entnahme_keyword(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await create_user(db_session, "svc-shareholder@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id, description_col="Verwendungszweck")
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(
            db_session,
            mandant.id,
            name="Gesellschafterkonto",
            iban="DE44500105175407324931",
        )
        await ensure_base_service(db_session, partner.id)
        service = await _create_service(db_session, partner.id, "Privatentnahme", pattern="entnahme")

        csv_bytes = make_csv([
            {
                "Valuta": "2026-02-05",
                "Buchungsdatum": "2026-02-05",
                "Betrag": "-500.00",
                "Auftraggeber": "Gesellschafterkonto",
                "IBAN": "DE44500105175407324931",
                "Verwendungszweck": "Private Entnahme Februar",
            }
        ])
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", csv_bytes, "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201

        await db_session.refresh(service)
        assert service.service_type == ServiceType.shareholder.value
        assert service.tax_rate == Decimal("0.00")

        review = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_type_review",
                    ReviewItem.service_id == service.id,
                )
            )
        ).first()
        assert review is not None
        assert review.context["auto_assigned_type"] == ServiceType.shareholder.value