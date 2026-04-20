"""Tests for Mandant CRUD and Account management (Bolt 003)."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import ImportRun, JournalLine, JournalLineSplit, ReviewItem, utcnow
from app.partners.models import AuditLog, Partner, PartnerName
from app.services.models import Service, ServiceMatcher, ServiceTypeKeyword
from app.tenants.models import Account, ColumnMappingConfig, Mandant
from tests.tenants.conftest import (
    assign_user_to_mandant,
    create_mandant,
    create_user,
    get_auth_token,
)


@pytest.mark.asyncio
class TestMandantCRUD:
    """Admin-only mandant management."""

    async def test_list_mandants_as_admin(self, client: AsyncClient, db_session: AsyncSession):
        admin = await create_user(db_session, "admin@test.com", UserRole.admin)
        await create_mandant(db_session, "Alpha GmbH")
        await create_mandant(db_session, "Beta GmbH")
        token = await get_auth_token(client, admin)
        resp = await client.get("/api/v1/mandants", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        names = [m["name"] for m in data]
        assert "Alpha GmbH" in names
        assert "Beta GmbH" in names

    async def test_create_mandant(self, client: AsyncClient, db_session: AsyncSession):
        admin = await create_user(db_session, "admin@test.com", UserRole.admin)
        token = await get_auth_token(client, admin)
        resp = await client.post(
            "/api/v1/mandants",
            json={"name": "New Corp"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "New Corp"

    async def test_non_admin_cannot_create_mandant(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)
        resp = await client.post(
            "/api/v1/mandants",
            json={"name": "Sneaky Corp"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_update_mandant(self, client: AsyncClient, db_session: AsyncSession):
        admin = await create_user(db_session, "admin@test.com", UserRole.admin)
        mandant = await create_mandant(db_session, "Old Name")
        token = await get_auth_token(client, admin)
        resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_deactivate_mandant_cascades_to_accounts(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.tenants.models import Account
        from datetime import datetime, timezone

        admin = await create_user(db_session, "admin@test.com", UserRole.admin)
        mandant = await create_mandant(db_session, "Corp to Deactivate")
        token = await get_auth_token(client, admin)

        # Create an account for this mandant
        now = datetime.now(timezone.utc)
        account = Account(
            mandant_id=mandant.id, name="Girokonto", currency="EUR",
            created_at=now, updated_at=now
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

        await db_session.refresh(mandant)
        await db_session.refresh(account)
        assert mandant.is_active is False
        assert account.is_active is False  # cascade (ADR-006)

    async def test_deactivate_nonexistent_mandant_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from uuid import uuid4
        admin = await create_user(db_session, "admin@test.com", UserRole.admin)
        token = await get_auth_token(client, admin)
        resp = await client.post(
            f"/api/v1/mandants/{uuid4()}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_cleanup_preview_lists_concrete_mandant_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        admin = await create_user(db_session, "cleanup-preview@test.com", UserRole.admin)
        token = await get_auth_token(client, admin)
        mandant = await create_mandant(db_session, "Cleanup GmbH")
        user = await create_user(db_session, "cleanup-user@test.com", UserRole.accountant)
        await assign_user_to_mandant(db_session, user, mandant)

        now = datetime.now(timezone.utc)
        account = Account(mandant_id=mandant.id, name="Main", currency="EUR", created_at=now, updated_at=now)
        db_session.add(account)
        await db_session.flush()

        db_session.add(ColumnMappingConfig(account_id=account.id, valuta_date_col="A", booking_date_col="B", amount_col="C", created_at=now, updated_at=now))

        partner = Partner(mandant_id=mandant.id, name="Partner A", created_at=utcnow(), updated_at=utcnow())
        db_session.add(partner)
        await db_session.flush()
        db_session.add(PartnerName(partner_id=partner.id, name="Partner Alias", created_at=utcnow()))

        service = Service(partner_id=partner.id, name="Beratung", service_type="supplier", tax_rate=Decimal("20.00"), created_at=utcnow(), updated_at=utcnow())
        db_session.add(service)
        await db_session.flush()
        db_session.add(ServiceMatcher(service_id=service.id, pattern="consulting", pattern_type="string", created_at=utcnow(), updated_at=utcnow()))

        run = ImportRun(account_id=account.id, mandant_id=mandant.id, user_id=user.id, filename="import.csv", status="completed", created_at=utcnow())
        db_session.add(run)
        await db_session.flush()

        line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            partner_id=partner.id,
            valuta_date="2026-04-01",
            booking_date="2026-04-01",
            amount=Decimal("10.00"),
            currency="EUR",
            text="Consulting",
            partner_name_raw="Partner A",
            created_at=utcnow(),
        )
        db_session.add(line)
        await db_session.flush()

        db_session.add(JournalLineSplit(
            journal_line_id=line.id, service_id=service.id,
            amount=Decimal("10.00"), assignment_mode="auto",
            amount_consistency_ok=False, created_at=utcnow(), updated_at=utcnow(),
        ))
        await db_session.flush()

        db_session.add(ReviewItem(mandant_id=mandant.id, item_type="service_assignment", journal_line_id=line.id, context={"reason": "multiple_matches"}, status="open", created_at=utcnow(), updated_at=utcnow()))
        db_session.add(AuditLog(mandant_id=mandant.id, event_type="journal.bulk_assign", actor_id=admin.id, payload={}, created_at=utcnow()))
        db_session.add(ServiceTypeKeyword(mandant_id=mandant.id, pattern="lohn", pattern_type="string", target_service_type="employee", created_at=utcnow(), updated_at=utcnow()))
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/cleanup-preview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert any(item["label"] == "Mandant" and item["count"] == 1 for item in body["delete_mandant"]["items"])
        assert any(item["label"] == "Buchungszeilen" and item["count"] == 1 for item in body["delete_data"]["items"])
        assert any(section["key"] == "journal_data" for section in body["selectable_sections"])

    async def test_cleanup_selected_journal_data_only_affects_target_mandant(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        admin = await create_user(db_session, "cleanup-journal@test.com", UserRole.admin)
        token = await get_auth_token(client, admin)
        mandant = await create_mandant(db_session, "Scope GmbH")
        other = await create_mandant(db_session, "Other GmbH")
        user = await create_user(db_session, "scope-user@test.com", UserRole.accountant)
        await assign_user_to_mandant(db_session, user, mandant)

        now = datetime.now(timezone.utc)
        account = Account(mandant_id=mandant.id, name="Main", currency="EUR", created_at=now, updated_at=now)
        other_account = Account(mandant_id=other.id, name="Other", currency="EUR", created_at=now, updated_at=now)
        db_session.add(account)
        db_session.add(other_account)
        await db_session.flush()

        run = ImportRun(account_id=account.id, mandant_id=mandant.id, user_id=user.id, filename="import.csv", status="completed", created_at=utcnow())
        other_run = ImportRun(account_id=other_account.id, mandant_id=other.id, user_id=admin.id, filename="other.csv", status="completed", created_at=utcnow())
        db_session.add(run)
        db_session.add(other_run)
        await db_session.flush()

        line = JournalLine(account_id=account.id, import_run_id=run.id, valuta_date="2026-04-01", booking_date="2026-04-01", amount=Decimal("10.00"), currency="EUR", created_at=utcnow())
        other_line = JournalLine(account_id=other_account.id, import_run_id=other_run.id, valuta_date="2026-04-01", booking_date="2026-04-01", amount=Decimal("20.00"), currency="EUR", created_at=utcnow())
        db_session.add(line)
        db_session.add(other_line)
        await db_session.flush()
        db_session.add(ReviewItem(mandant_id=mandant.id, item_type="name_match_with_iban", journal_line_id=line.id, context={}, status="open", created_at=utcnow(), updated_at=utcnow()))
        db_session.add(ReviewItem(mandant_id=other.id, item_type="name_match_with_iban", journal_line_id=other_line.id, context={}, status="open", created_at=utcnow(), updated_at=utcnow()))
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/cleanup",
            json={"mode": "selected", "scopes": ["journal_data"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        assert (await db_session.exec(select(JournalLine).where(JournalLine.account_id == account.id))).all() == []
        assert len((await db_session.exec(select(JournalLine).where(JournalLine.account_id == other_account.id))).all()) == 1

    async def test_cleanup_delete_data_keeps_mandant_but_removes_scoped_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        admin = await create_user(db_session, "cleanup-data@test.com", UserRole.admin)
        token = await get_auth_token(client, admin)
        mandant = await create_mandant(db_session, "Data GmbH")

        now = datetime.now(timezone.utc)
        account = Account(mandant_id=mandant.id, name="Main", currency="EUR", created_at=now, updated_at=now)
        db_session.add(account)
        await db_session.flush()
        db_session.add(ServiceTypeKeyword(mandant_id=mandant.id, pattern="steuer", pattern_type="string", target_service_type="authority", created_at=utcnow(), updated_at=utcnow()))
        db_session.add(AuditLog(mandant_id=mandant.id, event_type="x", actor_id=admin.id, payload={}, created_at=utcnow()))
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/cleanup",
            json={"mode": "delete_data"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        assert await db_session.get(Mandant, mandant.id) is not None
        assert (await db_session.exec(select(Account).where(Account.mandant_id == mandant.id))).all() == []
        assert (await db_session.exec(select(ServiceTypeKeyword).where(ServiceTypeKeyword.mandant_id == mandant.id))).all() == []
        assert (await db_session.exec(select(AuditLog).where(AuditLog.mandant_id == mandant.id))).all() == []

    async def test_cleanup_delete_mandant_removes_only_target_mandant(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        admin = await create_user(db_session, "cleanup-delete@test.com", UserRole.admin)
        token = await get_auth_token(client, admin)
        target = await create_mandant(db_session, "Delete Me")
        survivor = await create_mandant(db_session, "Keep Me")
        user = await create_user(db_session, "target-user@test.com", UserRole.viewer)
        await assign_user_to_mandant(db_session, user, target)

        resp = await client.post(
            f"/api/v1/mandants/{target.id}/cleanup",
            json={"mode": "delete_mandant"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert await db_session.get(Mandant, target.id) is None
        assert await db_session.get(Mandant, survivor.id) is not None


@pytest.mark.asyncio
class TestAccountCRUD:
    """Account management for mandant members."""

    async def test_create_account(self, client: AsyncClient, db_session: AsyncSession):
        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts",
            json={"name": "Girokonto", "currency": "EUR"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Girokonto"
        assert body["has_column_mapping"] is False

    async def test_iban_unique_on_create(self, client: AsyncClient, db_session: AsyncSession):
        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)
        iban = "DE89370400440532013000"
        await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts",
            json={"name": "Account 1", "iban": iban},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts",
            json={"name": "Account 2", "iban": iban},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_account_not_found_for_wrong_mandant(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from uuid import uuid4
        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/accounts/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_viewer_cannot_create_account(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts",
            json={"name": "Sneaky Account"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestColumnMapping:
    """Column mapping config UPSERT."""

    async def test_set_and_get_column_mapping(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from datetime import datetime, timezone
        from app.tenants.models import Account

        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)

        now = datetime.now(timezone.utc)
        account = Account(
            mandant_id=mandant.id, name="Girokonto", currency="EUR",
            created_at=now, updated_at=now
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        mapping_data = {
            "valuta_date_col": "Valuta",
            "booking_date_col": "Buchungsdatum",
            "amount_col": "Betrag",
            "delimiter": ";",
            "decimal_separator": ",",
            "date_format": "%d.%m.%Y",
            "encoding": "utf-8",
            "skip_rows": 1,
        }
        resp = await client.put(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/column-mapping",
            json=mapping_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valuta_date_col"] == "Valuta"
        assert body["skip_rows"] == 1

        # GET should return same config
        resp2 = await client.get(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/column-mapping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["valuta_date_col"] == "Valuta"

    async def test_upsert_updates_existing_mapping(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from datetime import datetime, timezone
        from app.tenants.models import Account

        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)

        now = datetime.now(timezone.utc)
        account = Account(
            mandant_id=mandant.id, name="Konto", currency="EUR",
            created_at=now, updated_at=now
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        base = {
            "valuta_date_col": "A", "booking_date_col": "B", "amount_col": "C",
        }
        await client.put(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/column-mapping",
            json=base, headers={"Authorization": f"Bearer {token}"},
        )
        # Update
        resp = await client.put(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/column-mapping",
            json={**base, "valuta_date_col": "NewColA"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["valuta_date_col"] == "NewColA"


@pytest.mark.asyncio
class TestRemapping:
    """Remapping trigger (ADR-007: async 202)."""

    async def test_trigger_remapping_returns_202(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from datetime import datetime, timezone
        from app.tenants.models import Account

        accountant = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, accountant, mandant)
        token = await get_auth_token(client, accountant)

        now = datetime.now(timezone.utc)
        account = Account(
            mandant_id=mandant.id, name="Konto", currency="EUR",
            created_at=now, updated_at=now
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/remap",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["message"] == "Remapping triggered"
        assert body["account_id"] == str(account.id)
