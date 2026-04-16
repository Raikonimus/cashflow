from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import ImportRun, ImportStatus, JournalLine, ReviewItem, utcnow
from app.services.models import ServiceGroup, ServiceGroupAssignment
from app.tenants.models import Account
from tests.partners.conftest import assign_user_to_mandant, create_mandant, create_user, get_auth_token


async def create_partner(client: AsyncClient, token: str, mandant_id, name: str = "Amazon EU") -> dict:
    resp = await client.post(
        f"/api/v1/mandants/{mandant_id}/partners",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
class TestServices:
    async def test_partner_has_base_service_after_creation(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["is_base_service"] is True
        assert items[0]["name"] == "Basisleistung"
        assert items[0]["journal_line_count"] == 0

    async def test_list_services_includes_current_journal_line_count(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc-count@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Hosting", "service_type": "supplier", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert service_resp.status_code == 201
        service_id = UUID(service_resp.json()["id"])

        account = Account(
            mandant_id=mandant.id,
            name="Hauptkonto",
            iban="AT001234567890123456",
            account_number="123456",
            bank_code="20111",
            currency="EUR",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        import_run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="import.csv",
            row_count=0,
            status=ImportStatus.completed.value,
            created_at=utcnow(),
            completed_at=utcnow(),
        )
        db_session.add(import_run)
        await db_session.flush()

        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(partner["id"]),
                service_id=service_id,
                valuta_date="2026-04-01",
                booking_date="2026-04-01",
                amount=Decimal("-50.00"),
                currency="EUR",
                text="Hosting April",
                partner_name_raw="Amazon EU",
                created_at=utcnow(),
            )
        )
        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(partner["id"]),
                service_id=service_id,
                valuta_date="2026-04-15",
                booking_date="2026-04-15",
                amount=Decimal("-75.00"),
                currency="EUR",
                text="Hosting Mai",
                partner_name_raw="Amazon EU",
                created_at=utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        hosting = next(item for item in items if item["id"] == str(service_id))
        assert hosting["journal_line_count"] == 2

    async def test_create_service(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Hosting", "service_type": "supplier", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Hosting"
        assert body["service_type"] == "supplier"
        assert body["is_base_service"] is False
        assert body["erfolgsneutral"] is False

        reviews = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_type_review",
                    ReviewItem.service_id == UUID(body["id"]),
                )
            )
        ).all()
        assert reviews == []
        assert body["service_type_manual"] is True
        assert body["tax_rate_manual"] is True

        patch_resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}/services/{body['id']}",
            json={"erfolgsneutral": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["erfolgsneutral"] is True

    async def test_create_shareholder_service(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc2b@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Gewinnausschüttung", "service_type": "shareholder", "tax_rate": "0.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["service_type"] == "shareholder"
        assert body["tax_rate"] == "0.00"

    async def test_base_service_name_cannot_be_changed(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc3@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        services_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        base_service_id = services_resp.json()[0]["id"]

        resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}/services/{base_service_id}",
            json={"name": "Renamed Base"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_base_service_cannot_be_deleted(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc4@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        services_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        base_service_id = services_resp.json()[0]["id"]

        resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/services/{base_service_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_base_service_cannot_have_matcher(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc5@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        services_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        base_service_id = services_resp.json()[0]["id"]

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{base_service_id}/matchers",
            json={"pattern": "amazon", "pattern_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_invalid_regex_matcher_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc6@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Amazon Marketplace", "service_type": "customer", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        service_id = service_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/matchers",
            json={"pattern": "[invalid((", "pattern_type": "regex"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_keyword_rules_can_be_created_and_listed(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc7@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        create_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/settings/service-keywords",
            json={"pattern": "Lohn", "pattern_type": "string", "target_service_type": "employee"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201

        list_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/settings/service-keywords",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        payload = list_resp.json()
        assert len(payload["items"]) == 1
        assert payload["items"][0]["pattern"] == "Lohn"
        assert len(payload["system_defaults"]) >= 1
        entnahme_rule = next((item for item in payload["system_defaults"] if item["pattern"] == "entnahme"), None)
        assert entnahme_rule is not None
        assert entnahme_rule["target_service_type"] == "shareholder"

    async def test_matcher_change_revalidates_existing_journal_lines(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc8@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        services_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        base_service_id = services_resp.json()[0]["id"]

        now = utcnow()
        account = Account(mandant_id=mandant.id, name="Girokonto", created_at=now, updated_at=now)
        db_session.add(account)
        await db_session.flush()

        run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="test.csv",
            status=ImportStatus.completed.value,
            created_at=now,
        )
        db_session.add(run)
        await db_session.flush()

        line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            partner_id=UUID(partner["id"]),
            service_id=UUID(base_service_id),
            service_assignment_mode="auto",
            valuta_date="2026-01-15",
            booking_date="2026-01-15",
            amount=Decimal("100.00"),
            currency="EUR",
            text="Hosting April",
            partner_name_raw="Amazon EU",
            created_at=now,
        )
        db_session.add(line)
        await db_session.commit()
        await db_session.refresh(line)

        create_service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Hosting", "service_type": "unknown", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_service_resp.status_code == 201
        service_id = create_service_resp.json()["id"]

        matcher_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/matchers",
            json={"pattern": "hosting", "pattern_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert matcher_resp.status_code == 201
        assert matcher_resp.json()["internal_only"] is False

        await db_session.refresh(line)
        assert str(line.service_id) == service_id
        assert line.service_assignment_mode == "auto"

        review = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_assignment",
                    ReviewItem.journal_line_id == line.id,
                )
            )
        ).first()
        assert review is None

    async def test_preview_matcher_excludes_lines_already_assigned_to_same_service(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc-preview@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        create_service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Hosting", "service_type": "unknown", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_service_resp.status_code == 201
        service_id = create_service_resp.json()["id"]

        now = utcnow()
        account = Account(mandant_id=mandant.id, name="Girokonto", created_at=now, updated_at=now)
        db_session.add(account)
        await db_session.flush()

        run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="test.csv",
            status=ImportStatus.completed.value,
            created_at=now,
        )
        db_session.add(run)
        await db_session.flush()

        line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            partner_id=UUID(partner["id"]),
            service_id=UUID(service_id),
            service_assignment_mode="auto",
            valuta_date="2026-02-15",
            booking_date="2026-02-15",
            amount=Decimal("100.00"),
            currency="EUR",
            text="Hosting April",
            partner_name_raw="Amazon EU",
            created_at=now,
        )
        db_session.add(line)
        await db_session.commit()

        preview_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/matchers/preview",
            json={"pattern": "hosting", "pattern_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert preview_resp.status_code == 200
        payload = preview_resp.json()
        assert payload["total"] == 0
        assert payload["matched_lines"] == []

    async def test_matcher_change_keeps_review_only_for_ambiguous_assignments(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc9@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)

        services_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        base_service_id = services_resp.json()[0]["id"]

        now = utcnow()
        account = Account(mandant_id=mandant.id, name="Girokonto", created_at=now, updated_at=now)
        db_session.add(account)
        await db_session.flush()

        run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="test.csv",
            status=ImportStatus.completed.value,
            created_at=now,
        )
        db_session.add(run)
        await db_session.flush()

        line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            partner_id=UUID(partner["id"]),
            service_id=UUID(base_service_id),
            service_assignment_mode="auto",
            valuta_date="2026-01-15",
            booking_date="2026-01-15",
            amount=Decimal("100.00"),
            currency="EUR",
            text="Hosting April",
            partner_name_raw="Amazon EU",
            created_at=now,
        )
        db_session.add(line)
        await db_session.commit()
        await db_session.refresh(line)

        first_service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Hosting", "service_type": "unknown", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first_service_resp.status_code == 201
        first_service_id = first_service_resp.json()["id"]

        second_service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "April Service", "service_type": "unknown", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second_service_resp.status_code == 201
        second_service_id = second_service_resp.json()["id"]

        first_matcher_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{first_service_id}/matchers",
            json={"pattern": "hosting", "pattern_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first_matcher_resp.status_code == 201

        second_matcher_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{second_service_id}/matchers",
            json={"pattern": "april", "pattern_type": "string"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second_matcher_resp.status_code == 201

        await db_session.refresh(line)
        assert str(line.service_id) == first_service_id

        review = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "service_assignment",
                    ReviewItem.journal_line_id == line.id,
                )
            )
        ).first()
        assert review is not None
        assert review.context["reason"] == "multiple_matches"
        assert review.context["current_service_id"] == first_service_id
        assert set(review.context["matching_services"]) == {first_service_id, second_service_id}

    async def test_internal_only_matcher_does_not_move_lines_from_other_partners(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc10@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        target_partner = await create_partner(client, token, mandant.id, name="Target Partner")
        source_partner = await create_partner(client, token, mandant.id, name="Source Partner")

        create_service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target_partner['id']}/services",
            json={"name": "Hosting", "service_type": "unknown", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_service_resp.status_code == 201
        service_id = create_service_resp.json()["id"]

        source_services_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners/{source_partner['id']}/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert source_services_resp.status_code == 200
        source_base_service_id = source_services_resp.json()[0]["id"]

        now = utcnow()
        account = Account(mandant_id=mandant.id, name="Girokonto", created_at=now, updated_at=now)
        db_session.add(account)
        await db_session.flush()

        run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="test.csv",
            status=ImportStatus.completed.value,
            created_at=now,
        )
        db_session.add(run)
        await db_session.flush()

        foreign_line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            partner_id=UUID(source_partner["id"]),
            service_id=UUID(source_base_service_id),
            service_assignment_mode="auto",
            valuta_date="2026-03-10",
            booking_date="2026-03-10",
            amount=Decimal("42.00"),
            currency="EUR",
            text="Hosting Gebühren",
            partner_name_raw="Source Partner",
            created_at=now,
        )
        db_session.add(foreign_line)
        await db_session.commit()
        await db_session.refresh(foreign_line)

        matcher_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/matchers",
            json={"pattern": "hosting", "pattern_type": "string", "internal_only": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert matcher_resp.status_code == 201
        assert matcher_resp.json()["internal_only"] is True

        await db_session.refresh(foreign_line)
        assert str(foreign_line.partner_id) == source_partner["id"]
        assert str(foreign_line.service_id) == source_base_service_id

    async def test_service_group_crud_and_assignment(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc-groups@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, name="Grouped Partner")

        created_service = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Lizenz", "service_type": "customer", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert created_service.status_code == 201
        service_id = created_service.json()["id"]

        list_income = await client.get(
            f"/api/v1/mandants/{mandant.id}/service-groups",
            params={"section": "income"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_income.status_code == 200
        assert len(list_income.json()) >= 1

        create_group = await client.post(
            f"/api/v1/mandants/{mandant.id}/service-groups",
            json={"section": "income", "name": "Lizenzen", "sort_order": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_group.status_code == 201
        group_id = create_group.json()["id"]

        assign_group = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/group-assignment",
            json={"service_group_id": group_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert assign_group.status_code == 200
        assert assign_group.json()["service_group_id"] == group_id

    async def test_cross_section_group_assignment_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc-cross@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, name="Cross Partner")

        service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Lizenz B", "service_type": "customer", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert service_resp.status_code == 201
        service_id = service_resp.json()["id"]

        expense_group_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/service-groups",
            json={"section": "expense", "name": "Buro", "sort_order": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert expense_group_resp.status_code == 201
        expense_group_id = expense_group_resp.json()["id"]

        assign_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/group-assignment",
            json={"service_group_id": expense_group_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert assign_resp.status_code == 422

    async def test_service_type_gets_matching_default_group_assignment(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc-default-group@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, name="Authority Partner")

        service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Finanzamt", "service_type": "authority", "tax_rate": "0.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert service_resp.status_code == 201
        service_id = service_resp.json()["id"]

        matrix_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/reports/income-expense",
            params={"year": 2026},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert matrix_resp.status_code == 200

        assignments = (
            await db_session.exec(
                select(ServiceGroupAssignment, ServiceGroup)
                .join(ServiceGroup, ServiceGroup.id == ServiceGroupAssignment.service_group_id)
                .where(ServiceGroupAssignment.mandant_id == mandant.id, ServiceGroupAssignment.service_id == UUID(service_id))
            )
        ).all()
        assert len(assignments) == 1
        _, assigned_group = assignments[0]
        assert assigned_group.section == "expense"
        assert assigned_group.name == "Behörden"

    async def test_default_group_assignment_updates_when_service_type_changes(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc-default-update@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, name="Expense Partner")

        service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Lieferant", "service_type": "supplier", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert service_resp.status_code == 201
        service_id = service_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}",
            json={"service_type": "authority"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200

        assignments = (
            await db_session.exec(
                select(ServiceGroupAssignment, ServiceGroup)
                .join(ServiceGroup, ServiceGroup.id == ServiceGroupAssignment.service_group_id)
                .where(ServiceGroupAssignment.mandant_id == mandant.id, ServiceGroupAssignment.service_id == UUID(service_id))
            )
        ).all()
        assert len(assignments) == 1
        _, assigned_group = assignments[0]
        assert assigned_group.name == "Behörden"

    async def test_manual_non_default_group_assignment_is_not_overwritten(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc-manual-group@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, name="Manual Group Partner")

        service_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
            json={"name": "Hosting", "service_type": "supplier", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert service_resp.status_code == 201
        service_id = service_resp.json()["id"]

        custom_group_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/service-groups",
            json={"section": "expense", "name": "Sonderkosten", "sort_order": 10},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert custom_group_resp.status_code == 201
        custom_group_id = custom_group_resp.json()["id"]

        assign_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}/group-assignment",
            json={"service_group_id": custom_group_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert assign_resp.status_code == 200

        patch_resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}/services/{service_id}",
            json={"service_type": "authority"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200

        matrix_resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/reports/income-expense",
            params={"year": 2026},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert matrix_resp.status_code == 200

        assignments = (
            await db_session.exec(
                select(ServiceGroupAssignment, ServiceGroup)
                .join(ServiceGroup, ServiceGroup.id == ServiceGroupAssignment.service_group_id)
                .where(ServiceGroupAssignment.mandant_id == mandant.id, ServiceGroupAssignment.service_id == UUID(service_id))
            )
        ).all()
        assert len(assignments) == 1
        _, assigned_group = assignments[0]
        assert assigned_group.name == "Sonderkosten"
        assert assigned_group.is_default is False
