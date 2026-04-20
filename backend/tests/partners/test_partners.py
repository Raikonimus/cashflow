"""Tests for Partner management (Bolt 004)."""
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from uuid import UUID

from app.auth.models import UserRole
from app.imports.models import ImportRun, JournalLine, JournalLineSplit, ReviewItem
from app.imports.models import utcnow as import_utcnow
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import Service, ServiceMatcher
from app.tenants.models import Account
from tests.partners.conftest import (
    assign_user_to_mandant,
    create_mandant,
    create_user,
    get_auth_token,
)


async def create_partner(
    client: AsyncClient,
    token: str,
    mandant_id,
    name: str = "Amazon EU",
    iban: str | None = None,
) -> dict:
    body: dict = {"name": name}
    if iban:
        body["iban"] = iban
    resp = await client.post(
        f"/api/v1/mandants/{mandant_id}/partners",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
class TestPartnerCRUD:

    async def test_create_partner(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        assert partner["name"] == "Amazon EU"
        assert partner["ibans"] == []

    async def test_create_partner_with_iban(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, iban="DE89370400440532013000")
        assert len(partner["ibans"]) == 1
        assert partner["ibans"][0]["iban"] == "DE89370400440532013000"

    async def test_duplicate_partner_name_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner(client, token, mandant.id, "Duplicate Corp")
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners",
            json={"name": "Duplicate Corp"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_viewer_cannot_create_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer, mandant)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners",
            json={"name": "Sneaky Partner"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_viewer_can_list_partners(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer, mandant)
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    async def test_list_partners_pagination(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        for i in range(5):
            await create_partner(client, token, mandant.id, f"Partner {i}")
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?page=1&size=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3
        assert body["pages"] == 2

    async def test_list_partners_includes_deduplicated_service_types(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, "Partner mit Leistungen")

        for name in ("Hosting", "Versand", "Gehalt"):
            service_type = "supplier" if name != "Gehalt" else "employee"
            resp = await client.post(
                f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/services",
                json={
                    "name": name,
                    "service_type": service_type,
                    "tax_rate": "20.00" if service_type == "supplier" else "0.00",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        listed_partner = next(item for item in items if item["id"] == partner["id"])
        assert listed_partner["service_types"] == ["supplier", "employee", "unknown"]

    async def test_list_partners_sorts_by_booking_count_desc(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "sort@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        frequent = await create_partner(client, token, mandant.id, "Frequent Partner")
        rare = await create_partner(client, token, mandant.id, "Rare Partner")

        account = Account(
            mandant_id=mandant.id,
            name="Main",
            bank_name="Bank",
            iban="DE44500105175407324931",
            bic="BANKDEFFXXX",
            created_at=import_utcnow(),
            updated_at=import_utcnow(),
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        import_run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="bookings.csv",
            status="completed",
            created_at=import_utcnow(),
        )
        db_session.add(import_run)
        await db_session.commit()
        await db_session.refresh(import_run)

        db_session.add_all([
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(frequent['id']),
                valuta_date="2026-04-01",
                booking_date="2026-04-01",
                amount=Decimal("-10.00"),
                currency="EUR",
                text="Booking 1",
                partner_name_raw="Frequent Partner",
                created_at=import_utcnow(),
            ),
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(frequent['id']),
                valuta_date="2026-04-02",
                booking_date="2026-04-02",
                amount=Decimal("-12.00"),
                currency="EUR",
                text="Booking 2",
                partner_name_raw="Frequent Partner",
                created_at=import_utcnow(),
            ),
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(rare['id']),
                valuta_date="2026-04-03",
                booking_date="2026-04-03",
                amount=Decimal("-8.00"),
                currency="EUR",
                text="Booking 3",
                partner_name_raw="Rare Partner",
                created_at=import_utcnow(),
            ),
        ])
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?include_inactive=true&sort_by=journal_line_count&sort_dir=desc",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["id"] == frequent["id"]
        assert items[0]["journal_line_count"] == 2
        assert items[1]["id"] == rare["id"]

    async def test_list_partners_filters_by_service_type(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "filter@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        shareholder_partner = await create_partner(client, token, mandant.id, "Gesellschafter Partner")
        supplier_partner = await create_partner(client, token, mandant.id, "Lieferant Partner")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{shareholder_partner['id']}/services",
            json={"name": "Entnahme", "service_type": "shareholder", "tax_rate": "0.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{supplier_partner['id']}/services",
            json={"name": "Hosting", "service_type": "supplier", "tax_rate": "20.00"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?include_inactive=true&service_type=shareholder",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == shareholder_partner["id"]
        assert items[0]["service_types"] == ["shareholder", "unknown"]

    async def test_delete_partner_without_bookings(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, "Delete Me")

        resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 204
        deleted_partner = await db_session.get(Partner, UUID(partner["id"]))
        assert deleted_partner is None

    async def test_delete_partner_with_bookings_returns_409(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, "Booked Partner")

        account = Account(
            mandant_id=mandant.id,
            name="Main",
            bank_name="Bank",
            iban="DE44500105175407324931",
            bic="BANKDEFFXXX",
            created_at=import_utcnow(),
            updated_at=import_utcnow(),
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        import_run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="bookings.csv",
            status="completed",
            created_at=import_utcnow(),
        )
        db_session.add(import_run)
        await db_session.commit()
        await db_session.refresh(import_run)

        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(partner['id']),
                valuta_date="2026-04-01",
                booking_date="2026-04-01",
                amount=Decimal("-10.00"),
                currency="EUR",
                text="Test booking",
                partner_name_raw="Booked Partner",
                created_at=import_utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 409
        assert "Move the bookings first" in resp.json()["detail"]

    async def test_delete_inactive_partner_cleans_dependents_without_orphans(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc3@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner_payload = await create_partner(client, token, mandant.id, "Cleanup Partner")
        partner_id = UUID(partner_payload["id"])

        partner = await db_session.get(Partner, partner_id)
        assert partner is not None
        partner.is_active = False
        db_session.add(partner)
        await db_session.commit()

        account = Account(
            mandant_id=mandant.id,
            name="Cleanup Account",
            bank_name="Bank",
            iban="DE44500105175407324931",
            bic="BANKDEFFXXX",
            created_at=import_utcnow(),
            updated_at=import_utcnow(),
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        import_run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="cleanup.csv",
            status="completed",
            created_at=import_utcnow(),
        )
        db_session.add(import_run)
        await db_session.commit()
        await db_session.refresh(import_run)

        base_service = (
            await db_session.exec(
                select(Service).where(Service.partner_id == partner_id, Service.is_base_service == True)  # noqa: E712
            )
        ).first()
        assert base_service is not None

        matcher = ServiceMatcher(
            service_id=base_service.id,
            pattern="cleanup",
            pattern_type="string",
            created_at=import_utcnow(),
            updated_at=import_utcnow(),
        )
        db_session.add(matcher)

        db_session.add(PartnerIban(partner_id=partner_id, iban="AT611904300234573201", created_at=import_utcnow()))
        db_session.add(PartnerAccount(partner_id=partner_id, account_number="1234567", blz="19043", created_at=import_utcnow()))
        db_session.add(PartnerName(partner_id=partner_id, name="Cleanup Alias", created_at=import_utcnow()))

        line = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=partner_id,
            valuta_date="2026-04-01",
            booking_date="2026-04-01",
            amount=Decimal("-10.00"),
            currency="EUR",
            text="Cleanup booking",
            partner_name_raw="Cleanup Partner",
            created_at=import_utcnow(),
        )
        db_session.add(line)
        await db_session.commit()
        await db_session.refresh(line)

        db_session.add(JournalLineSplit(
            journal_line_id=line.id, service_id=base_service.id,
            amount=Decimal("-10.00"), assignment_mode="auto",
            amount_consistency_ok=False, created_at=import_utcnow(), updated_at=import_utcnow(),
        ))
        await db_session.commit()

        review = ReviewItem(
            mandant_id=mandant.id,
            item_type="service_type_review",
            service_id=base_service.id,
            status="open",
            created_at=import_utcnow(),
            updated_at=import_utcnow(),
        )
        db_session.add(review)
        await db_session.commit()

        resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/partners/{partner_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

        deleted_partner = await db_session.get(Partner, partner_id)
        assert deleted_partner is None

        service_after = await db_session.get(Service, base_service.id)
        assert service_after is None

        matcher_after = await db_session.get(ServiceMatcher, matcher.id)
        assert matcher_after is None

        review_after = await db_session.get(ReviewItem, review.id)
        assert review_after is None

        await db_session.refresh(line)
        assert line.partner_id is None
        remaining_splits = (await db_session.exec(
            select(JournalLineSplit).where(JournalLineSplit.journal_line_id == line.id)
        )).all()
        assert remaining_splits == []

        ibans = (await db_session.exec(select(PartnerIban).where(PartnerIban.partner_id == partner_id))).all()
        accounts = (await db_session.exec(select(PartnerAccount).where(PartnerAccount.partner_id == partner_id))).all()
        names = (await db_session.exec(select(PartnerName).where(PartnerName.partner_id == partner_id))).all()
        assert ibans == []
        assert accounts == []
        assert names == []


@pytest.mark.asyncio
class TestPartnerIban:

    async def test_add_iban_to_partner(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/ibans",
            json={"iban": "DE89 3704 0044 0532 0130 00"},  # with spaces
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["iban"] == "DE89370400440532013000"  # normalized

    async def test_global_iban_uniqueness(self, client: AsyncClient, db_session: AsyncSession):
        """ADR-008: IBAN must be globally unique across all partners."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        p1 = await create_partner(client, token, mandant.id, "Partner 1")
        p2 = await create_partner(client, token, mandant.id, "Partner 2")
        iban = "LU96013000000726000067"
        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{p1['id']}/ibans",
            json={"iban": iban}, headers={"Authorization": f"Bearer {token}"}
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{p2['id']}/ibans",
            json={"iban": iban}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 409

    async def test_add_iban_with_reassign_moves_only_matching_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner(client, token, mandant.id, "IBAN Quelle")
        target = await create_partner(client, token, mandant.id, "IBAN Ziel")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        line_matching = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=UUID(source["id"]),
            valuta_date="2026-04-03",
            booking_date="2026-04-03",
            amount=Decimal("-33.00"),
            currency="EUR",
            text="Passende IBAN-Zeile",
            partner_name_raw="IBAN Quelle",
            partner_iban_raw="IE31CITI99005127256228",
            created_at=import_utcnow(),
        )
        line_other = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=UUID(source["id"]),
            valuta_date="2026-04-04",
            booking_date="2026-04-04",
            amount=Decimal("-44.00"),
            currency="EUR",
            text="Andere IBAN-Zeile",
            partner_name_raw="IBAN Quelle",
            partner_iban_raw="DE89370400440532013000",
            created_at=import_utcnow(),
        )
        db_session.add_all([line_matching, line_other])
        await db_session.commit()
        await db_session.refresh(line_matching)
        await db_session.refresh(line_other)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/ibans?reassign=true",
            json={"iban": "IE31CITI99005127256228"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        await db_session.refresh(line_matching)
        await db_session.refresh(line_other)
        assert line_matching.partner_id == UUID(target["id"])
        assert line_other.partner_id == UUID(source["id"])


@pytest.mark.asyncio
class TestPartnerNameVariants:

    async def test_add_name_variant(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/names",
            json={"name": "AMZ MARKETPLACE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "AMZ MARKETPLACE"

    async def test_duplicate_name_within_partner_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/names",
            json={"name": "Duplicate"}, headers={"Authorization": f"Bearer {token}"}
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/names",
            json={"name": "Duplicate"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 409




@pytest.mark.asyncio
class TestPartnerSearch:

    async def test_search_by_name(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner(client, token, mandant.id, "Amazon EU")
        await create_partner(client, token, mandant.id, "Rewe GmbH")

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?search=amazon",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Amazon EU"

    async def test_search_by_iban(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner(client, token, mandant.id, "Amazon EU", iban="DE89370400440532013000")
        await create_partner(client, token, mandant.id, "Rewe GmbH")

        # Suche nach vollständiger normalisierter IBAN
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?search=DE89370400440532013000",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Amazon EU"

    async def test_search_by_iban_with_spaces(self, client: AsyncClient, db_session: AsyncSession):
        """IBAN mit Leerzeichen im Suchbegriff soll normalisiert verglichen werden."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner(client, token, mandant.id, "Amazon EU", iban="DE89370400440532013000")

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?search=DE89 3704 0044 0532 0130 00",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Amazon EU"

    async def test_search_no_match_returns_empty(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner(client, token, mandant.id, "Amazon EU")

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?search=Unbekannt",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


async def _create_account_and_import_run(db_session, mandant_id, user_id) -> tuple:
    """Hilfsfunktion: legt Account + ImportRun an und gibt beide zurück."""
    from app.imports.models import utcnow as import_utcnow
    account = Account(
        mandant_id=mandant_id,
        name="Main",
        bank_name="Bank",
        iban="DE02500105170137075030",
        bic="BANKDEFFXXX",
        created_at=import_utcnow(),
        updated_at=import_utcnow(),
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    import_run = ImportRun(
        account_id=account.id,
        mandant_id=mandant_id,
        user_id=user_id,
        filename="bookings.csv",
        status="completed",
        created_at=import_utcnow(),
    )
    db_session.add(import_run)
    await db_session.commit()
    await db_session.refresh(import_run)
    return account, import_run


@pytest.mark.asyncio
class TestAccountPreviewAndReassign:

    async def test_preview_returns_matching_lines_from_other_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.imports.models import utcnow as import_utcnow
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner(client, token, mandant.id, "Quelle GmbH")
        target = await create_partner(client, token, mandant.id, "Ziel GmbH")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(source["id"]),
                valuta_date="2026-01-15",
                booking_date="2026-01-15",
                amount=Decimal("-50.00"),
                currency="EUR",
                text="Zahlung via Konto",
                partner_name_raw="Quelle GmbH",
                partner_account_raw="12345678",
                created_at=import_utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/accounts/preview",
            json={"account_number": "12345678"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["matched_lines"][0]["partner_name_raw"] == "Quelle GmbH"
        assert body["matched_lines"][0]["current_partner_name"] == "Quelle GmbH"
        assert body["matched_lines"][0]["already_assigned"] is False

    async def test_preview_includes_own_lines_as_already_assigned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Zeilen die bereits diesem Partner gehören erscheinen mit already_assigned=True."""
        from app.imports.models import utcnow as import_utcnow
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner(client, token, mandant.id, "Eigener Partner")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(partner["id"]),
                valuta_date="2026-01-20",
                booking_date="2026-01-20",
                amount=Decimal("-30.00"),
                currency="EUR",
                text="Eigene Buchung",
                partner_name_raw="Eigener Partner",
                partner_account_raw="77889900",
                created_at=import_utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/accounts/preview",
            json={"account_number": "77889900"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["matched_lines"][0]["already_assigned"] is True

    async def test_preview_returns_empty_when_no_matches(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, "Niemand AG")

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/accounts/preview",
            json={"account_number": "99999999"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["matched_lines"] == []

    async def test_add_account_with_reassign_transfers_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.imports.models import utcnow as import_utcnow
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner(client, token, mandant.id, "Alt GmbH")
        target = await create_partner(client, token, mandant.id, "Neu GmbH")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        line = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=UUID(source["id"]),
            valuta_date="2026-02-01",
            booking_date="2026-02-01",
            amount=Decimal("-100.00"),
            currency="EUR",
            text="Überweisung",
            partner_name_raw="Alt GmbH",
            partner_account_raw="55667788",
            created_at=import_utcnow(),
        )
        db_session.add(line)
        await db_session.commit()
        await db_session.refresh(line)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/accounts?reassign=true",
            json={"account_number": "55667788"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        await db_session.refresh(line)
        assert line.partner_id == UUID(target["id"])

    async def test_add_account_with_reassign_deletes_empty_source_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        from app.imports.models import utcnow as import_utcnow
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner(client, token, mandant.id, "Leerer Partner")
        target = await create_partner(client, token, mandant.id, "Voller Partner")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=import_run.id,
                partner_id=UUID(source["id"]),
                valuta_date="2026-03-01",
                booking_date="2026-03-01",
                amount=Decimal("-25.00"),
                currency="EUR",
                text="Einzige Buchung",
                partner_name_raw="Leerer Partner",
                partner_account_raw="11223344",
                created_at=import_utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/accounts?reassign=true",
            json={"account_number": "11223344"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        # Source-Partner wurde gelöscht (nicht nur deaktiviert)
        source_partner = await db_session.get(Partner, UUID(source["id"]))
        assert source_partner is None

    async def test_add_account_with_reassign_moves_only_matching_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Nur Zeilen mit passender Kontonummer werden verschoben."""
        from app.imports.models import utcnow as import_utcnow
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        source = await create_partner(client, token, mandant.id, "Misch Partner")
        target = await create_partner(client, token, mandant.id, "Ziel Partner")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        # Zeile 1: passt zur Kontonummer
        line_matching = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=UUID(source["id"]),
            valuta_date="2026-04-01",
            booking_date="2026-04-01",
            amount=Decimal("-10.00"),
            currency="EUR",
            text="Passende Zeile",
            partner_name_raw="Misch Partner",
            partner_account_raw="99887766",
            created_at=import_utcnow(),
        )
        # Zeile 2: gehört demselben Partner, andere Kontonummer
        line_other = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=UUID(source["id"]),
            valuta_date="2026-04-02",
            booking_date="2026-04-02",
            amount=Decimal("-20.00"),
            currency="EUR",
            text="Andere Kontonummer",
            partner_name_raw="Misch Partner",
            partner_account_raw="11111111",
            created_at=import_utcnow(),
        )
        db_session.add_all([line_matching, line_other])
        await db_session.commit()
        await db_session.refresh(line_matching)
        await db_session.refresh(line_other)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/accounts?reassign=true",
            json={"account_number": "99887766"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        # Nur die passende Zeile wird verschoben
        await db_session.refresh(line_matching)
        await db_session.refresh(line_other)
        assert line_matching.partner_id == UUID(target["id"])
        assert line_other.partner_id == UUID(source["id"])

    async def test_add_account_with_reassign_assigns_unpartnered_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Zeilen ohne Partner (partner_id=NULL) werden dem neuen Partner zugeordnet.
        SQL NULL != UUID ergibt NULL (falsy) – muss explizit behandelt werden."""
        from app.imports.models import utcnow as import_utcnow
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        target = await create_partner(client, token, mandant.id, "Erste Bank")
        account, import_run = await _create_account_and_import_run(db_session, mandant.id, user.id)

        # Zeile ohne Partner (wie "kein Partner"-Review-Einträge)
        line = JournalLine(
            account_id=account.id,
            import_run_id=import_run.id,
            partner_id=None,
            valuta_date="2026-04-10",
            booking_date="2026-04-10",
            amount=Decimal("-55.00"),
            currency="EUR",
            text="Unbekannte Buchung",
            partner_name_raw=None,
            partner_account_raw="49900997173",
            created_at=import_utcnow(),
        )
        db_session.add(line)
        await db_session.commit()
        await db_session.refresh(line)

        # Preview muss 1 Zeile zeigen (already_assigned=False, weil partner_id=None)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/accounts/preview",
            json={"account_number": "49900997173"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        preview = resp.json()
        assert preview["total"] == 1
        assert preview["matched_lines"][0]["already_assigned"] is False

        # Hinzufügen mit reassign=true → Zeile wird dem Partner zugeordnet
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{target['id']}/accounts?reassign=true",
            json={"account_number": "49900997173"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        await db_session.refresh(line)
        assert line.partner_id == UUID(target["id"])
