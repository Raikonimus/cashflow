"""Tests for Journal & Audit (Bolt 009)."""
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
    create_partner_db,
    create_user,
    get_auth_token,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── List Journal Lines ───────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestListJournalLines:

    async def test_returns_empty_list_when_no_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_returns_lines_for_mandant(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        token = await get_auth_token(client, user, mandant)

        await create_journal_line_db(db_session, account.id, run.id)
        await create_journal_line_db(
            db_session, account.id, run.id, valuta_date="2025-02-20"
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    async def test_filter_by_account_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "v@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        acc1 = await create_account_db(db_session, mandant.id, "Konto 1")
        acc2 = await create_account_db(db_session, mandant.id, "Konto 2")
        run1 = await create_import_run_db(db_session, acc1.id, mandant.id, user.id)
        run2 = await create_import_run_db(db_session, acc2.id, mandant.id, user.id)
        await create_journal_line_db(db_session, acc1.id, run1.id)
        await create_journal_line_db(db_session, acc2.id, run2.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            params={"account_id": str(acc1.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["account_id"] == str(acc1.id)

    async def test_filter_by_year(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "v@t.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        acc = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, acc.id, mandant.id, user.id)
        await create_journal_line_db(db_session, acc.id, run.id, valuta_date="2024-12-01")
        await create_journal_line_db(db_session, acc.id, run.id, valuta_date="2025-03-10")
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            params={"year": 2025},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_filter_by_year_and_month(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "v2@t.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        acc = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, acc.id, mandant.id, user.id)
        await create_journal_line_db(db_session, acc.id, run.id, valuta_date="2025-03-10")
        await create_journal_line_db(db_session, acc.id, run.id, valuta_date="2025-04-01")
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            params={"year": 2025, "month": 3},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_filter_has_partner_false(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "v3@t.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        acc = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, acc.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id)
        await create_journal_line_db(db_session, acc.id, run.id, partner_id=partner.id)
        await create_journal_line_db(db_session, acc.id, run.id, partner_id=None)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            params={"has_partner": False},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["partner_id"] is None

    async def test_filter_by_account_cross_mandant_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "v@t.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        other_mandant = await create_mandant(db_session, "Andere GmbH")
        await assign_user_to_mandant(db_session, user, mandant)
        other_acc = await create_account_db(db_session, other_mandant.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal",
            params={"account_id": str(other_acc.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        mandant = await create_mandant(db_session)
        resp = await client.get(f"/api/v1/mandants/{mandant.id}/journal")
        assert resp.status_code == 401


# ─── Bulk-Assign ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBulkAssign:

    async def test_assigns_partner_to_multiple_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        acc = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, acc.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id)
        line1 = await create_journal_line_db(db_session, acc.id, run.id)
        line2 = await create_journal_line_db(db_session, acc.id, run.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/bulk-assign",
            json={"line_ids": [str(line1.id), str(line2.id)], "partner_id": str(partner.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned"] == 2
        assert data["skipped"] == 0

    async def test_skips_already_assigned_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        acc = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, acc.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id)
        line1 = await create_journal_line_db(
            db_session, acc.id, run.id, partner_id=partner.id
        )
        line2 = await create_journal_line_db(db_session, acc.id, run.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/bulk-assign",
            json={"line_ids": [str(line1.id), str(line2.id)], "partner_id": str(partner.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned"] == 1
        assert data["skipped"] == 1

    async def test_cross_mandant_line_ids_return_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc3@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        other_mandant = await create_mandant(db_session, "Andere GmbH")
        await assign_user_to_mandant(db_session, user, mandant)
        own_acc = await create_account_db(db_session, mandant.id)
        other_acc = await create_account_db(db_session, other_mandant.id)
        own_user = await create_user(db_session, "other@test.com")
        run_other = await create_import_run_db(
            db_session, other_acc.id, other_mandant.id, own_user.id
        )
        foreign_line = await create_journal_line_db(
            db_session, other_acc.id, run_other.id
        )
        partner = await create_partner_db(db_session, mandant.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/bulk-assign",
            json={
                "line_ids": [str(foreign_line.id)],
                "partner_id": str(partner.id),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_bulk_assign(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        import uuid
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/bulk-assign",
            json={"line_ids": [str(uuid.uuid4())], "partner_id": str(uuid.uuid4())},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_empty_line_ids_returns_zero(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc4@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        partner = await create_partner_db(db_session, mandant.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/bulk-assign",
            json={"line_ids": [], "partner_id": str(partner.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["assigned"] == 0


# ─── Audit Log ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuditLog:

    async def test_mandant_admin_can_list_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "admin@test.com", UserRole.mandant_admin)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/audit",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0

    async def test_accountant_cannot_list_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/audit",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_bulk_assign_creates_audit_log_entry(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        admin = await create_user(db_session, "admin2@test.com", UserRole.mandant_admin)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, admin, mandant)
        acc = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, acc.id, mandant.id, admin.id)
        partner = await create_partner_db(db_session, mandant.id)
        line = await create_journal_line_db(db_session, acc.id, run.id)
        token = await get_auth_token(client, admin, mandant)

        await client.post(
            f"/api/v1/mandants/{mandant.id}/journal/bulk-assign",
            json={"line_ids": [str(line.id)], "partner_id": str(partner.id)},
            headers=_auth(token),
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/audit",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(i["event_type"] == "journal.bulk_assign" for i in items)
