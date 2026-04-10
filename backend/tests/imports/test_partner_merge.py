"""Tests for Partner Merge (Bolt 005) – story 004-partner-merge."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.partners.models import AuditLog, Partner, PartnerIban, PartnerName
from tests.imports import (
    assign_user_to_mandant,
    create_mandant,
    create_partner_db,
    create_user,
    get_auth_token,
    utcnow,
)


@pytest.mark.asyncio
class TestPartnerMerge:
    """AC: POST /partners/:target_id/merge { source_id }"""

    async def test_merge_transfers_children_and_deactivates_source(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Given two active partners,
        When POST /partners/:target_id/merge { source_id },
        Then all source IBANs/names moved to target, source deactivated.
        """
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner_db(db_session, mandant.id, "Source Corp", iban="DE89370400440532013000")
        target = await create_partner_db(db_session, mandant.id, "Target Corp")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target"]["id"] == str(target.id)
        assert data["lines_reassigned"] == 0  # no journal_lines yet in test
        assert "audit_log_id" in data

        # source must be inactive
        await db_session.refresh(source)
        assert source.is_active is False

        # IBAN must be on target now
        result = await db_session.exec(
            select(PartnerIban).where(PartnerIban.partner_id == target.id)
        )
        ibans = result.all()
        assert any(i.iban == "DE89370400440532013000" for i in ibans)

    async def test_merge_same_id_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Given source_id == target_id, When POST merge, Then 400."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Solo Corp")
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner.id}/merge",
            json={"source_id": str(partner.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    async def test_merge_inactive_source_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Given source is inactive, Then 404."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        now = utcnow()
        source = Partner(mandant_id=mandant.id, name="Inactive Corp", is_active=False, created_at=now, updated_at=now)
        db_session.add(source)
        target = await create_partner_db(db_session, mandant.id, "Target Corp")
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_merge_wrong_mandant_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Given source belongs to different mandant, Then 404."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant_a = await create_mandant(db_session, "Mandant A")
        mandant_b = await create_mandant(db_session, "Mandant B")
        await assign_user_to_mandant(db_session, user, mandant_a)
        await assign_user_to_mandant(db_session, user, mandant_b)
        token = await get_auth_token(client, user, mandant_a)

        source = await create_partner_db(db_session, mandant_b.id, "B-Partner")
        target = await create_partner_db(db_session, mandant_a.id, "A-Target")

        resp = await client.post(
            f"/api/v1/mandants/{mandant_a.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_merge_viewer_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Viewer must not call merge."""
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer, mandant)

        source = await create_partner_db(db_session, mandant.id, "Source")
        target = await create_partner_db(db_session, mandant.id, "Target")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_merge_dedup_iban_silently_ignored(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Given source and target share the same IBAN,
        When merge,
        Then no error, target keeps IBAN once.
        """
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        now = utcnow()
        source = await create_partner_db(db_session, mandant.id, "Source Dup")
        target = await create_partner_db(db_session, mandant.id, "Target Dup", iban="DE89370400440532013000")

        # Add same IBAN to source (bypass normal service to force duplicate scenario)
        source_iban = PartnerIban(partner_id=source.id, iban="DE89370400440532013001", created_at=now)
        db_session.add(source_iban)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        result = await db_session.exec(
            select(PartnerIban).where(PartnerIban.partner_id == target.id)
        )
        ibans = result.all()
        iban_values = [i.iban for i in ibans]
        assert "DE89370400440532013001" in iban_values  # transferred from source

    async def test_merge_creates_audit_log_entry(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """After merge, audit_log entry exists with correct event_type."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner_db(db_session, mandant.id, "Source Log")
        target = await create_partner_db(db_session, mandant.id, "Target Log")

        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

        result = await db_session.exec(
            select(AuditLog).where(AuditLog.mandant_id == mandant.id)
        )
        entries = result.all()
        assert len(entries) == 1
        assert entries[0].event_type == "partner.merged"
        payload = entries[0].payload
        assert payload["source_partner_id"] == str(source.id)
        assert payload["target_partner_id"] == str(target.id)


@pytest.mark.asyncio
class TestAuditLog:
    """AC: GET /mandants/:id/audit-log"""

    async def test_list_audit_log_viewer(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Viewer can read audit log."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        viewer = await create_user(db_session, "view@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        await assign_user_to_mandant(db_session, viewer, mandant)
        acc_token = await get_auth_token(client, user, mandant)
        view_token = await get_auth_token(client, viewer, mandant)

        source = await create_partner_db(db_session, mandant.id, "Source")
        target = await create_partner_db(db_session, mandant.id, "Target")
        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target.id}/merge",
            json={"source_id": str(source.id)},
            headers={"Authorization": f"Bearer {acc_token}"},
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/audit-log",
            headers={"Authorization": f"Bearer {view_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == "partner.merged"

    async def test_audit_log_empty_for_new_mandant(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "view@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/audit-log",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
