"""Tests for ReviewService and review API endpoints (Bolt 008)."""
# pylint: disable=redefined-outer-name,unused-import
from decimal import Decimal
from datetime import timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import JournalLine, ReviewItem, utcnow
from app.partners.models import AuditLog, Partner, PartnerIban
from app.services.models import Service, ServiceType

from tests.review import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_account_db,
    create_mandant,
    create_partner_db,
    create_user,
    db_session,
    get_auth_token,
    setup_db,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_review_item(
    session: AsyncSession,
    mandant_id,
    partner_id=None,
    iban_raw: str | None = "DE89370400440532013000",
    name_raw: str | None = "Amazon EU",
    status: str = "open",
) -> tuple[JournalLine, ReviewItem]:
    now = utcnow()
    line = JournalLine(
        id=uuid4(),
        account_id=uuid4(),
        import_run_id=uuid4(),
        partner_id=partner_id,
        valuta_date="2026-01-15",
        booking_date="2026-01-15",
        amount=Decimal("100.00"),
        currency="EUR",
        partner_iban_raw=iban_raw,
        partner_name_raw=name_raw,
        created_at=now,
    )
    session.add(line)
    await session.flush()

    item = ReviewItem(
        mandant_id=mandant_id,
        item_type="name_match_with_iban",
        journal_line_id=line.id,
        context={"matched_on": "name", "raw_name": name_raw, "raw_iban": iban_raw},
        status=status,
        created_at=now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(line)
    await session.refresh(item)
    return line, item


async def _create_service(
    session: AsyncSession,
    partner_id,
    name: str,
    service_type: str = ServiceType.unknown.value,
    tax_rate: Decimal = Decimal("20.00"),
) -> Service:
    now = utcnow()
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type=service_type,
        tax_rate=tax_rate,
        created_at=now,
        updated_at=now,
    )
    session.add(service)
    await session.flush()
    return service


async def _create_service_assignment_review_item(
    session: AsyncSession,
    mandant_id,
    partner_id,
    current_service_id,
    proposed_service_id,
    reason: str = "matcher_changed",
) -> tuple[JournalLine, ReviewItem]:
    now = utcnow()
    line = JournalLine(
        id=uuid4(),
        account_id=uuid4(),
        import_run_id=uuid4(),
        partner_id=partner_id,
        service_id=current_service_id,
        service_assignment_mode="auto",
        valuta_date="2026-01-15",
        booking_date="2026-01-15",
        amount=Decimal("100.00"),
        currency="EUR",
        text="Hosting April",
        partner_name_raw="Amazon EU",
        created_at=now,
    )
    session.add(line)
    await session.flush()

    item = ReviewItem(
        mandant_id=mandant_id,
        item_type="service_assignment",
        journal_line_id=line.id,
        context={
            "current_service_id": str(current_service_id),
            "proposed_service_id": str(proposed_service_id) if proposed_service_id else None,
            "reason": reason,
        },
        status="open",
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(line)
    await session.refresh(item)
    return line, item


async def _create_service_type_review_item(
    session: AsyncSession,
    mandant_id,
    partner_id,
    previous_type: str = ServiceType.unknown.value,
    auto_assigned_type: str = ServiceType.employee.value,
) -> tuple[Service, ReviewItem, list[JournalLine]]:
    now = utcnow()
    service = Service(
        partner_id=partner_id,
        name="Lohnlauf",
        service_type=auto_assigned_type,
        tax_rate=Decimal("0.00"),
        created_at=now,
        updated_at=now,
    )
    session.add(service)
    await session.flush()

    lines: list[JournalLine] = []
    for amount in (Decimal("-1500.00"), Decimal("-1750.00")):
        line = JournalLine(
            id=uuid4(),
            account_id=uuid4(),
            import_run_id=uuid4(),
            partner_id=partner_id,
            service_id=service.id,
            service_assignment_mode="auto",
            valuta_date="2026-01-31",
            booking_date="2026-01-31",
            amount=amount,
            currency="EUR",
            text="Lohn Januar",
            partner_name_raw="Payroll GmbH",
            created_at=now,
        )
        session.add(line)
        lines.append(line)
    await session.flush()

    item = ReviewItem(
        mandant_id=mandant_id,
        item_type="service_type_review",
        service_id=service.id,
        context={
            "previous_type": previous_type,
            "auto_assigned_type": auto_assigned_type,
            "reason": "keyword:lohn",
            "current_journal_line_ids": [str(line.id) for line in lines],
        },
        status="open",
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(service)
    await session.refresh(item)
    for line in lines:
        await session.refresh(line)
    return service, item, lines


async def _create_archived_review_item(
    session: AsyncSession,
    mandant_id,
    status: str,
    *,
    item_type: str = "service_assignment",
    resolved_by=None,
    resolved_at=None,
) -> ReviewItem:
    now = utcnow()
    item = ReviewItem(
        mandant_id=mandant_id,
        item_type=item_type,
        context={"reason": "archived"},
        status=status,
        created_at=now,
        updated_at=resolved_at or now,
        resolved_by=resolved_by,
        resolved_at=resolved_at or now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


# ---------------------------------------------------------------------------
# GET /review — list
# ---------------------------------------------------------------------------

class TestListReviewItems:
    async def test_returns_open_items_by_default(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        _, item = await _create_review_item(db_session, mandant.id, partner_id=partner.id)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(item.id)
        assert data["items"][0]["status"] == "open"

    async def test_filter_by_status_confirmed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Partner A")
        await _create_review_item(db_session, mandant.id, partner_id=partner.id, status="open")
        await _create_review_item(db_session, mandant.id, partner_id=partner.id, status="confirmed")

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review?status=confirmed",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["status"] == "confirmed"

    async def test_filter_all_returns_every_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "P")
        await _create_review_item(db_session, mandant.id, partner_id=partner.id, status="open")
        await _create_review_item(db_session, mandant.id, partner_id=partner.id, status="adjusted")

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review?status=all",
            headers=_auth(token),
        )
        assert resp.json()["total"] == 2

    async def test_empty_list_on_no_items(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    async def test_viewer_gets_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_name_match_with_iban_includes_enriched_iban_context(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "iban-review@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        db_session.add(PartnerIban(partner_id=partner.id, iban="DE12500105170648489890"))
        await db_session.commit()

        _, item = await _create_review_item(
            db_session,
            mandant.id,
            partner_id=partner.id,
            iban_raw="DE89370400440532013000",
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        review_item = next(entry for entry in resp.json()["items"] if entry["id"] == str(item.id))

        assert review_item["context"]["raw_iban"] == "DE89370400440532013000"
        assert review_item["context"]["matched_partner_ibans"] == ["DE12500105170648489890"]
        assert review_item["context"]["matched_partner_iban_count"] == 1
        assert review_item["context"]["diagnosis"]["iban"]["provided"] is True
        assert review_item["context"]["diagnosis"]["iban"]["normalized"] == "DE89370400440532013000"
        assert review_item["context"]["diagnosis"]["iban"]["matches_partner_iban"] is False


# ---------------------------------------------------------------------------
# POST /review/{id}/confirm
# ---------------------------------------------------------------------------

class TestConfirmReviewItem:
    async def test_confirm_sets_status_and_resolved_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        _, item = await _create_review_item(
            db_session, mandant.id, partner_id=partner.id, iban_raw="DE89370400440532013000"
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["resolved_by"] == str(user.id)
        assert data["resolved_at"] is not None

    async def test_confirm_registers_iban_on_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """ADR-013: confirm adds partner_iban_raw to partner_ibans."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Neue Firma")
        _, item = await _create_review_item(
            db_session, mandant.id, partner_id=partner.id, iban_raw="DE89370400440532013000"
        )

        await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )

        ibans = (
            await db_session.exec(
                select(PartnerIban).where(PartnerIban.partner_id == partner.id)
            )
        ).all()
        assert len(ibans) == 1
        assert ibans[0].iban == "DE89370400440532013000"

    async def test_confirm_iban_idempotent(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Confirming when IBAN already registered must not create duplicate."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(
            db_session, mandant.id, "Amazon EU", iban="DE89370400440532013000"
        )
        _, item = await _create_review_item(
            db_session, mandant.id, partner_id=partner.id, iban_raw="DE89370400440532013000"
        )

        await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )

        ibans = (
            await db_session.exec(
                select(PartnerIban).where(PartnerIban.partner_id == partner.id)
            )
        ).all()
        assert len(ibans) == 1  # still only one

    async def test_confirm_already_confirmed_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """ADR-014: confirmed item cannot be processed again."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Corp")
        _, item = await _create_review_item(
            db_session, mandant.id, partner_id=partner.id, status="confirmed"
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 409

    async def test_confirm_writes_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Firma X")
        _, item = await _create_review_item(db_session, mandant.id, partner_id=partner.id)

        await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )

        entries = (
            await db_session.exec(
                select(AuditLog).where(
                    AuditLog.mandant_id == mandant.id,
                    AuditLog.event_type == "review.confirmed",
                )
            )
        ).all()
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# POST /review/{id}/reassign
# ---------------------------------------------------------------------------

class TestReassignReviewItem:
    async def test_reassign_updates_journal_line_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        old_partner = await create_partner_db(db_session, mandant.id, "Wrong Partner")
        new_partner = await create_partner_db(db_session, mandant.id, "Correct Partner")
        line, item = await _create_review_item(
            db_session, mandant.id, partner_id=old_partner.id
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reassign",
            json={"partner_id": str(new_partner.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "adjusted"

        await db_session.refresh(line)
        assert line.partner_id == new_partner.id

    async def test_reassign_writes_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        old_partner = await create_partner_db(db_session, mandant.id, "P1")
        new_partner = await create_partner_db(db_session, mandant.id, "P2")
        _, item = await _create_review_item(db_session, mandant.id, partner_id=old_partner.id)

        await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reassign",
            json={"partner_id": str(new_partner.id)},
            headers=_auth(token),
        )

        entries = (
            await db_session.exec(
                select(AuditLog).where(AuditLog.event_type == "review.reassigned")
            )
        ).all()
        assert len(entries) == 1
        assert entries[0].payload["new_partner_id"] == str(new_partner.id)

    async def test_reassign_to_nonexistent_partner_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Existing")
        _, item = await _create_review_item(db_session, mandant.id, partner_id=partner.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reassign",
            json={"partner_id": str(uuid4())},
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_reassign_already_adjusted_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "P")
        new_partner = await create_partner_db(db_session, mandant.id, "P2")
        _, item = await _create_review_item(
            db_session, mandant.id, partner_id=partner.id, status="adjusted"
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reassign",
            json={"partner_id": str(new_partner.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 409

    async def test_reassign_deletes_other_open_reviews_for_same_line(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc-reassign@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        old_partner = await create_partner_db(db_session, mandant.id, "Wrong Partner")
        new_partner = await create_partner_db(db_session, mandant.id, "Correct Partner")
        current_service = await _create_service(db_session, old_partner.id, "Altservice")
        proposed_service = await _create_service(db_session, old_partner.id, "Vorschlag")
        line, item = await _create_review_item(
            db_session, mandant.id, partner_id=old_partner.id
        )
        line.service_id = current_service.id
        line.service_assignment_mode = "auto"
        db_session.add(line)
        await db_session.flush()
        db_session.add(
            ReviewItem(
                mandant_id=mandant.id,
                item_type="service_assignment",
                journal_line_id=line.id,
                context={
                    "current_service_id": str(current_service.id),
                    "proposed_service_id": str(proposed_service.id),
                    "reason": "matcher_changed",
                },
                status="open",
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reassign",
            json={"partner_id": str(new_partner.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        remaining = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.journal_line_id == line.id,
                    ReviewItem.item_type == "service_assignment",
                    ReviewItem.status == "open",
                )
            )
        ).all()
        assert not any(review.context.get("reason") == "matcher_changed" for review in remaining)


# ---------------------------------------------------------------------------
# POST /review/{id}/new-partner
# ---------------------------------------------------------------------------

class TestNewPartnerReviewItem:
    async def test_new_partner_creates_partner_and_assigns(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        old_partner = await create_partner_db(db_session, mandant.id, "Old")
        line, item = await _create_review_item(db_session, mandant.id, partner_id=old_partner.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/new-partner",
            json={"name": "Brand New GmbH"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "adjusted"

        await db_session.refresh(line)
        new_partner = await db_session.get(Partner, line.partner_id)
        assert new_partner is not None
        assert new_partner.name == "Brand New GmbH"
        assert new_partner.mandant_id == mandant.id
        assert new_partner.is_active is True

    async def test_new_partner_writes_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Existing")
        _, item = await _create_review_item(db_session, mandant.id, partner_id=partner.id)

        await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/new-partner",
            json={"name": "New Corp"},
            headers=_auth(token),
        )

        entries = (
            await db_session.exec(
                select(AuditLog).where(
                    AuditLog.event_type == "review.new_partner_assigned"
                )
            )
        ).all()
        assert len(entries) == 1
        assert entries[0].payload["partner_name"] == "New Corp"

    async def test_new_partner_does_not_register_iban(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """ADR-013: IBAN auto-registration only on confirm, not new-partner."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        old_partner = await create_partner_db(db_session, mandant.id, "Old Inc")
        line, item = await _create_review_item(
            db_session, mandant.id, partner_id=old_partner.id, iban_raw="DE89370400440532013000"
        )

        await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/new-partner",
            json={"name": "Fresh GmbH"},
            headers=_auth(token),
        )

        await db_session.refresh(line)
        ibans = (
            await db_session.exec(
                select(PartnerIban).where(PartnerIban.partner_id == line.partner_id)
            )
        ).all()
        assert len(ibans) == 0  # no IBAN auto-registered


class TestServiceAssignmentReviewItem:
    async def test_list_includes_service_assignment_context_and_line_details(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-review@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        proposed_service = await _create_service(db_session, partner.id, "Hosting")
        line, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            proposed_service.id,
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        review_item = next(entry for entry in resp.json()["items"] if entry["id"] == str(item.id))
        assert review_item["context"]["current_service_id"] == str(current_service.id)
        assert review_item["context"]["current_service_name"] == "Basisleistung"
        assert review_item["context"]["proposed_service_id"] == str(proposed_service.id)
        assert review_item["context"]["proposed_service_name"] == "Hosting"
        assert review_item["journal_line"]["id"] == str(line.id)
        assert review_item["journal_line"]["partner_name"] == "Amazon EU"
        assert review_item["journal_line"]["service_id"] == str(current_service.id)

    async def test_confirm_assigns_proposed_service_and_sets_manual_mode(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-confirm@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        proposed_service = await _create_service(db_session, partner.id, "Hosting")
        line, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            proposed_service.id,
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

        await db_session.refresh(line)
        assert line.service_id == proposed_service.id
        assert line.service_assignment_mode == "manual"

    async def test_adjust_assigns_selected_service_and_sets_manual_mode(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-adjust@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        selected_service = await _create_service(db_session, partner.id, "Hosting")
        line, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            None,
            reason="multiple_matches",
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/adjust",
            json={"service_id": str(selected_service.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "adjusted"

        await db_session.refresh(line)
        assert line.service_id == selected_service.id
        assert line.service_assignment_mode == "manual"

    async def test_adjust_rejects_service_from_other_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-invalid@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        other_partner = await create_partner_db(db_session, mandant.id, "Other")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        foreign_service = await _create_service(db_session, other_partner.id, "Fremdleistung")
        _, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            None,
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/adjust",
            json={"service_id": str(foreign_service.id)},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_confirm_keeps_open_service_type_review_for_assigned_service(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-confirm-type@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        proposed_service = await _create_service(db_session, partner.id, "Hosting")
        line, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            proposed_service.id,
        )

        type_review = ReviewItem(
            mandant_id=mandant.id,
            item_type="service_type_review",
            service_id=proposed_service.id,
            context={
                "previous_type": ServiceType.unknown.value,
                "auto_assigned_type": ServiceType.supplier.value,
                "reason": "amount<=0",
                "current_journal_line_ids": [str(line.id)],
            },
            status="open",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(type_review)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        remaining_type_review = await db_session.get(ReviewItem, type_review.id)
        assert remaining_type_review is not None
        assert remaining_type_review.status == "open"

    async def test_confirm_keeps_open_service_type_review_for_previous_service(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-confirm-prev-type@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        proposed_service = await _create_service(db_session, partner.id, "Hosting")
        _, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            proposed_service.id,
        )

        type_review = ReviewItem(
            mandant_id=mandant.id,
            item_type="service_type_review",
            service_id=current_service.id,
            context={
                "previous_type": ServiceType.unknown.value,
                "auto_assigned_type": ServiceType.supplier.value,
                "reason": "amount<=0",
                "current_journal_line_ids": [],
            },
            status="open",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(type_review)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        remaining_type_review = await db_session.get(ReviewItem, type_review.id)
        assert remaining_type_review is not None
        assert remaining_type_review.status == "open"

    async def test_reject_keeps_assignment_unchanged(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-reject@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Amazon EU")
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        proposed_service = await _create_service(db_session, partner.id, "Hosting")
        line, item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            proposed_service.id,
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reject",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        await db_session.refresh(line)
        assert line.service_id == current_service.id
        assert line.service_assignment_mode == "auto"


class TestServiceTypeReviewItem:
    async def test_list_can_filter_service_type_reviews_only(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-type-filter@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Payroll GmbH")
        service, type_item, _ = await _create_service_type_review_item(db_session, mandant.id, partner.id)
        current_service = await _create_service(db_session, partner.id, "Basisleistung")
        _, assignment_item = await _create_service_assignment_review_item(
            db_session,
            mandant.id,
            partner.id,
            current_service.id,
            service.id,
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review?item_type=service_type_review",
            headers=_auth(token),
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert [item["id"] for item in payload["items"]] == [str(type_item.id)]
        assert str(assignment_item.id) not in {item["id"] for item in payload["items"]}

    async def test_list_hides_legacy_open_service_type_reviews_without_context(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-type-legacy@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Payroll GmbH")
        service = await _create_service(db_session, partner.id, "Altbestand")
        legacy_item = ReviewItem(
            mandant_id=mandant.id,
            item_type="service_type_review",
            service_id=service.id,
            context={},
            status="open",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(legacy_item)
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review?item_type=service_type_review",
            headers=_auth(token),
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["items"] == []
    async def test_get_review_detail_includes_service_and_assigned_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-type-detail@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Payroll GmbH")
        service, item, lines = await _create_service_type_review_item(db_session, mandant.id, partner.id)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["service_id"] == str(service.id)
        assert payload["service"]["partner_name"] == "Payroll GmbH"
        assert payload["context"]["previous_type"] == ServiceType.unknown.value
        assert payload["context"]["auto_assigned_type"] == ServiceType.employee.value
        assert payload["service"]["tax_rate"] == "0.00"
        assert {entry["id"] for entry in payload["assigned_journal_lines"]} == {str(line.id) for line in lines}

    async def test_confirm_marks_service_type_manual(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-type-confirm@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Payroll GmbH")
        service, item, _ = await _create_service_type_review_item(db_session, mandant.id, partner.id)
        service.service_type_manual = False
        db_session.add(service)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

        await db_session.refresh(service)
        assert service.service_type == ServiceType.employee.value
        assert service.service_type_manual is True

    async def test_adjust_updates_service_type_and_tax_rate(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-type-adjust@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Payroll GmbH")
        service, item, _ = await _create_service_type_review_item(db_session, mandant.id, partner.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/adjust",
            json={"service_type": "authority", "tax_rate": "10.00", "erfolgsneutral": True},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "adjusted"

        await db_session.refresh(service)
        assert service.service_type == ServiceType.authority.value
        assert service.service_type_manual is True
        assert service.tax_rate == Decimal("10.00")
        assert service.tax_rate_manual is True
        assert service.erfolgsneutral is True

    async def test_viewer_cannot_confirm_service_type_review(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "svc-type-viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner = await create_partner_db(db_session, mandant.id, "Payroll GmbH")
        _, item, _ = await _create_service_type_review_item(db_session, mandant.id, partner.id)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/confirm",
            headers=_auth(token),
        )
        assert resp.status_code == 403


class TestReviewArchive:
    async def test_archive_returns_only_resolved_items_sorted_by_resolved_at_desc(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "archive@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        older = await _create_archived_review_item(
            db_session,
            mandant.id,
            "confirmed",
            resolved_by=user.id,
            resolved_at=utcnow() - timedelta(days=2),
        )
        newer = await _create_archived_review_item(
            db_session,
            mandant.id,
            "rejected",
            resolved_by=user.id,
            resolved_at=utcnow() - timedelta(days=1),
        )
        await _create_review_item(db_session, mandant.id, status="open")

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review/archive",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 2
        assert [item["id"] for item in payload["items"]] == [str(newer.id), str(older.id)]

    async def test_archive_filters_by_item_type_and_resolved_by_and_date_range(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "archive-filter@test.com", UserRole.accountant)
        other_user = await create_user(db_session, "archive-other@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        await assign_user_to_mandant(db_session, other_user, mandant)
        token = await get_auth_token(client, user, mandant)

        within = await _create_archived_review_item(
            db_session,
            mandant.id,
            "adjusted",
            item_type="service_type_review",
            resolved_by=user.id,
            resolved_at=utcnow() - timedelta(days=1),
        )
        await _create_archived_review_item(
            db_session,
            mandant.id,
            "confirmed",
            item_type="service_assignment",
            resolved_by=user.id,
            resolved_at=utcnow() - timedelta(days=1),
        )
        await _create_archived_review_item(
            db_session,
            mandant.id,
            "rejected",
            item_type="service_type_review",
            resolved_by=other_user.id,
            resolved_at=utcnow() - timedelta(days=10),
        )

        target_day = (utcnow() - timedelta(days=1)).date().isoformat()
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/review/archive"
            f"?item_type=service_type_review&resolved_by_user_id={user.id}"
            f"&resolved_from={target_day}&resolved_to={target_day}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == str(within.id)

    async def test_write_action_on_archived_item_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "archive-write@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        item = await _create_archived_review_item(
            db_session,
            mandant.id,
            "confirmed",
            resolved_by=user.id,
        )

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/reject",
            headers=_auth(token),
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# manual_service_assignment review items
# ---------------------------------------------------------------------------

async def _create_partner_with_base_service(
    session: AsyncSession, mandant_id, name: str, *, manual_assignment: bool = False
) -> tuple["Partner", "Service"]:
    from app.services.service import ensure_base_service
    partner = await create_partner_db(session, mandant_id, name)
    partner.manual_assignment = manual_assignment
    session.add(partner)
    await session.flush()
    base = await ensure_base_service(session, partner.id)
    await session.commit()
    await session.refresh(partner)
    await session.refresh(base)
    return partner, base


async def _add_journal_line_on_service(
    session: AsyncSession, partner_id, service_id, text: str = "Test"
) -> JournalLine:
    line = JournalLine(
        id=uuid4(),
        account_id=uuid4(),
        import_run_id=uuid4(),
        partner_id=partner_id,
        service_id=service_id,
        service_assignment_mode="auto",
        valuta_date="2026-03-01",
        booking_date="2026-03-01",
        amount=Decimal("-99.00"),
        currency="EUR",
        text=text,
        created_at=utcnow(),
    )
    session.add(line)
    await session.commit()
    await session.refresh(line)
    return line


class TestManualServiceAssignmentReview:
    async def test_adjust_assigns_service_and_archives_item(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Adjusting a manual_service_assignment item with a service_id assigns the
        journal line to that service and moves the review item to the archive."""
        user = await create_user(db_session, "msa-adjust@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner, base_service = await _create_partner_with_base_service(
            db_session, mandant.id, "Test GmbH", manual_assignment=True
        )
        line = await _add_journal_line_on_service(db_session, partner.id, base_service.id)

        # Create manual_service_assignment review item
        item = ReviewItem(
            mandant_id=mandant.id,
            item_type="manual_service_assignment",
            journal_line_id=line.id,
            context={},
            status="open",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(item)

        # Create a non-base service to assign to
        other_service = Service(
            partner_id=partner.id,
            name="Hosting",
            service_type=ServiceType.supplier.value,
            tax_rate=Decimal("20.00"),
            is_base_service=False,
            service_type_manual=True,
            tax_rate_manual=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(other_service)
        await db_session.commit()
        await db_session.refresh(item)
        await db_session.refresh(other_service)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/adjust",
            headers=_auth(token),
            json={"service_id": str(other_service.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "adjusted"

        # Journal line should now point to other_service
        await db_session.refresh(line)
        assert str(line.service_id) == str(other_service.id)
        assert line.service_assignment_mode == "manual"

    async def test_adjust_requires_service_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Adjusting without service_id returns 422."""
        user = await create_user(db_session, "msa-no-svc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner, base_service = await _create_partner_with_base_service(
            db_session, mandant.id, "Test GmbH 2", manual_assignment=True
        )
        line = await _add_journal_line_on_service(db_session, partner.id, base_service.id)

        item = ReviewItem(
            mandant_id=mandant.id,
            item_type="manual_service_assignment",
            journal_line_id=line.id,
            context={},
            status="open",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{item.id}/adjust",
            headers=_auth(token),
            json={"service_type": "supplier"},
        )
        assert resp.status_code == 422

    async def test_setting_manual_assignment_true_creates_review_items(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """When manual_assignment is set to True via PATCH /partners/:id,
        review items are created for all lines currently on the base service."""
        user = await create_user(db_session, "msa-flip-true@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner, base_service = await _create_partner_with_base_service(
            db_session, mandant.id, "Trigger GmbH", manual_assignment=False
        )
        line1 = await _add_journal_line_on_service(db_session, partner.id, base_service.id, "Buchung 1")
        line2 = await _add_journal_line_on_service(db_session, partner.id, base_service.id, "Buchung 2")

        # Confirm no review items yet
        existing = (
            await db_session.exec(
                select(ReviewItem).where(ReviewItem.item_type == "manual_service_assignment")
            )
        ).all()
        assert len(existing) == 0

        resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}/partners/{partner.id}",
            headers=_auth(token),
            json={"manual_assignment": True},
        )
        assert resp.status_code == 200

        created = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "manual_service_assignment",
                    ReviewItem.status == "open",
                    ReviewItem.mandant_id == mandant.id,
                )
            )
        ).all()
        line_ids = {str(r.journal_line_id) for r in created}
        assert str(line1.id) in line_ids
        assert str(line2.id) in line_ids

    async def test_setting_manual_assignment_false_deletes_review_items(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """When manual_assignment is set to False, all open manual_service_assignment
        review items for the partner are deleted."""
        user = await create_user(db_session, "msa-flip-false@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        partner, base_service = await _create_partner_with_base_service(
            db_session, mandant.id, "Flip False GmbH", manual_assignment=True
        )
        line = await _add_journal_line_on_service(db_session, partner.id, base_service.id)

        item = ReviewItem(
            mandant_id=mandant.id,
            item_type="manual_service_assignment",
            journal_line_id=line.id,
            context={},
            status="open",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db_session.add(item)
        await db_session.commit()

        resp = await client.patch(
            f"/api/v1/mandants/{mandant.id}/partners/{partner.id}",
            headers=_auth(token),
            json={"manual_assignment": False},
        )
        assert resp.status_code == 200

        remaining = (
            await db_session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "manual_service_assignment",
                    ReviewItem.status == "open",
                )
            )
        ).all()
        assert len(remaining) == 0
