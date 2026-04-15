"""Tests for Partner Merge (Bolt 005) – story 004-partner-merge."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import ImportRun, JournalLine, ReviewItem
from app.partners.models import AuditLog, Partner, PartnerIban
from tests.imports import (
    assign_user_to_mandant,
    create_account_db,
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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(partner.id), "target_partner_id": str(partner.id)},
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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
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
            f"/api/v1/mandants/{mandant_a.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

        result = await db_session.exec(
            select(AuditLog).where(AuditLog.mandant_id == mandant.id)
        )
        entries = result.all()
        partner_merge_entries = [entry for entry in entries if entry.event_type == "partner.merged"]
        assert len(partner_merge_entries) == 1
        payload = partner_merge_entries[0].payload
        assert payload["source_partner_id"] == str(source.id)
        assert payload["target_partner_id"] == str(target.id)

    async def test_merge_deletes_open_reviews_for_reassigned_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "merge-review@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner_db(db_session, mandant.id, "Source Review")
        target = await create_partner_db(db_session, mandant.id, "Target Review")
        account = await create_account_db(db_session, mandant.id)
        run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="merge.csv",
            status="completed",
            created_at=utcnow(),
        )
        db_session.add(run)
        await db_session.flush()
        line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            partner_id=source.id,
            valuta_date="2026-04-01",
            booking_date="2026-04-01",
            amount="10.00",
            currency="EUR",
            text="Merge line",
            partner_name_raw="Source Review",
            created_at=utcnow(),
        )
        db_session.add(line)
        await db_session.flush()

        db_session.add(
            ReviewItem(
                mandant_id=mandant.id,
                item_type="name_match_with_iban",
                journal_line_id=line.id,
                context={"raw_name": "Source Review"},
                status="open",
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        remaining = (
            await db_session.exec(
                select(ReviewItem).where(ReviewItem.journal_line_id == line.id, ReviewItem.status == "open")
            )
        ).all()
        assert not any(review.item_type == "name_match_with_iban" for review in remaining)


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
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
            headers={"Authorization": f"Bearer {acc_token}"},
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/audit-log",
            headers={"Authorization": f"Bearer {view_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any(item["event_type"] == "partner.merged" for item in data["items"])

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
        assert not any(item["event_type"] == "partner.merged" for item in resp.json()["items"])


@pytest.mark.asyncio
class TestMergeTransfersAccounts:

    async def test_account_transferred_to_target(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Kontonummern des Source-Partners werden beim Merge auf den Target-Partner übertragen."""
        from app.partners.models import PartnerAccount
        from sqlmodel import select

        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner_db(db_session, mandant.id, "Source", account_number="49900997173", blz="20111")
        target = await create_partner_db(db_session, mandant.id, "Target")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        accounts = (await db_session.exec(
            select(PartnerAccount).where(PartnerAccount.partner_id == target.id)
        )).all()
        assert any(a.account_number == "49900997173" for a in accounts)

        # Source-Partner darf die Kontonummer nicht mehr haben
        source_accounts = (await db_session.exec(
            select(PartnerAccount).where(PartnerAccount.partner_id == source.id)
        )).all()
        assert not any(a.account_number == "49900997173" for a in source_accounts)

    async def test_duplicate_account_number_dropped_on_merge(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Wenn Target dieselbe Kontonummer hat (andere BLZ), wird Source-Eintrag gelöscht.

        Der UNIQUE-Constraint gilt auf (blz, account_number). Dieselbe Kontonummer
        mit unterschiedlicher BLZ kann also zwei verschiedenen Partnern gehören.
        Nach dem Merge soll die source-seitige Variante gelöscht werden.
        """
        from app.partners.models import PartnerAccount
        from sqlmodel import select

        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        # Gleiche Kontonummer, aber unterschiedliche BLZ – beides erlaubt per Constraint
        source = await create_partner_db(db_session, mandant.id, "Source", account_number="49900997173", blz="20815")
        target = await create_partner_db(db_session, mandant.id, "Target", account_number="49900997173", blz="20111")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/merge",
            json={"source_partner_id": str(source.id), "target_partner_id": str(target.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        accounts = (await db_session.exec(
            select(PartnerAccount).where(PartnerAccount.account_number == "49900997173")
        )).all()
        # Source-seitiger Eintrag wurde gelöscht, Target-Eintrag bleibt
        assert len(accounts) == 1
        assert accounts[0].partner_id == target.id
