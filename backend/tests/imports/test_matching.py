"""Tests for PartnerMatchingService and ReviewItemFactory (Bolt 007)."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.matching import MatchOutcome, PartnerMatchingService, ReviewItemFactory
from app.imports.models import JournalLine, utcnow
from app.partners.models import Partner, PartnerIban, PartnerName

# Re-use shared fixtures from the imports package
from tests.imports import (  # noqa: F401
    create_mandant,
    db_session,
    setup_db,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_active_partner(
    session: AsyncSession,
    mandant_id,
    name: str,
    iban: str | None = None,
    alias: str | None = None,
) -> Partner:
    now = utcnow()
    partner = Partner(mandant_id=mandant_id, name=name, is_active=True, created_at=now, updated_at=now)
    session.add(partner)
    await session.flush()
    if iban:
        session.add(PartnerIban(partner_id=partner.id, iban=iban, created_at=now))
    if alias:
        session.add(PartnerName(partner_id=partner.id, name=alias, created_at=now))
    await session.commit()
    await session.refresh(partner)
    return partner


async def _create_inactive_partner(
    session: AsyncSession,
    mandant_id,
    name: str,
    iban: str | None = None,
    alias: str | None = None,
) -> Partner:
    now = utcnow()
    partner = Partner(mandant_id=mandant_id, name=name, is_active=False, created_at=now, updated_at=now)
    session.add(partner)
    await session.flush()
    if iban:
        session.add(PartnerIban(partner_id=partner.id, iban=iban, created_at=now))
    if alias:
        session.add(PartnerName(partner_id=partner.id, name=alias, created_at=now))
    await session.commit()
    await session.refresh(partner)
    return partner


def _make_journal_line(
    mandant_id=None,
    partner_id=None,
    iban_raw: str | None = None,
    name_raw: str | None = None,
) -> JournalLine:
    return JournalLine(
        id=uuid4(),
        account_id=uuid4(),
        import_run_id=uuid4(),
        partner_id=partner_id,
        valuta_date="2026-01-15",
        booking_date="2026-01-15",
        amount=Decimal("99.00"),
        currency="EUR",
        partner_iban_raw=iban_raw,
        partner_name_raw=name_raw,
    )


# ---------------------------------------------------------------------------
# PartnerMatchingService — IBAN match
# ---------------------------------------------------------------------------

class TestIbanMatch:
    async def test_iban_match_returns_iban_outcome(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)
        partner = await _create_active_partner(
            db_session, mandant.id, "Amazon EU", iban="DE89370400440532013000"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw=None,
        )

        assert result.outcome == MatchOutcome.iban_match
        assert result.partner_id == partner.id
        assert result.review_context is None

    async def test_iban_normalised_before_lookup(self, db_session: AsyncSession):
        """IBANs with spaces should still match the stored normalised form."""
        mandant = await create_mandant(db_session)
        partner = await _create_active_partner(
            db_session, mandant.id, "REWE", iban="DE89370400440532013000"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="DE89 3704 0044 0532 0130 00",
            name_raw=None,
        )

        assert result.outcome == MatchOutcome.iban_match
        assert result.partner_id == partner.id

    async def test_iban_match_ignored_for_inactive_partner(self, db_session: AsyncSession):
        """ADR-011: inactive partners must never be matched by IBAN."""
        mandant = await create_mandant(db_session)
        await _create_inactive_partner(
            db_session, mandant.id, "Old Corp", iban="DE89370400440532013000"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw=None,
        )

        # Must fall through to new_partner, not iban_match
        assert result.outcome == MatchOutcome.new_partner

    async def test_iban_not_matched_across_mandants(self, db_session: AsyncSession):
        """An IBAN registered under another mandant must not match."""
        other_mandant = await create_mandant(db_session, "Other GmbH")
        await _create_active_partner(
            db_session, other_mandant.id, "Fremdfirma", iban="DE89370400440532013000"
        )

        own_mandant = await create_mandant(db_session, "Own AG")
        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=own_mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw=None,
        )

        assert result.outcome == MatchOutcome.new_partner


# ---------------------------------------------------------------------------
# PartnerMatchingService — Name match
# ---------------------------------------------------------------------------

class TestNameMatch:
    async def test_name_match_case_insensitive(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)
        partner = await _create_active_partner(
            db_session, mandant.id, "Amazon EU", alias="amazon eu"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw="amazon eu",
        )

        assert result.outcome == MatchOutcome.name_match
        assert result.partner_id == partner.id
        assert result.review_context is not None
        assert result.review_context["matched_on"] == "name"

    async def test_name_match_ignored_for_inactive_partner(self, db_session: AsyncSession):
        """ADR-011: inactive partners must never be matched by name."""
        mandant = await create_mandant(db_session)
        await _create_inactive_partner(
            db_session, mandant.id, "Old Corp", alias="Old Corp"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw="Old Corp",
        )

        assert result.outcome == MatchOutcome.new_partner

    async def test_iban_takes_priority_over_name(self, db_session: AsyncSession):
        """When both IBAN and name would match (different partners), IBAN wins."""
        mandant = await create_mandant(db_session)
        iban_partner = await _create_active_partner(
            db_session, mandant.id, "IBAN Partner", iban="DE89370400440532013000"
        )
        await _create_active_partner(
            db_session, mandant.id, "Name Partner", alias="Name Partner"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw="Name Partner",
        )

        assert result.outcome == MatchOutcome.iban_match
        assert result.partner_id == iban_partner.id


# ---------------------------------------------------------------------------
# PartnerMatchingService — New partner creation
# ---------------------------------------------------------------------------

class TestNewPartner:
    async def test_no_match_creates_new_partner(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw="Unbekannte Firma",
        )

        assert result.outcome == MatchOutcome.new_partner
        assert result.partner_id is not None

        # Verify the Partner row was actually persisted
        partner = await db_session.get(Partner, result.partner_id)
        assert partner is not None
        assert partner.name == "Unbekannte Firma"
        assert partner.is_active is True
        assert partner.mandant_id == mandant.id

    async def test_no_name_no_iban_creates_unknown_partner(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)

        svc = PartnerMatchingService(db_session)
        result = await svc.match(mandant_id=mandant.id, iban_raw=None, name_raw=None)

        assert result.outcome == MatchOutcome.new_partner
        partner = await db_session.get(Partner, result.partner_id)
        assert partner is not None
        assert partner.name == "Unknown"


# ---------------------------------------------------------------------------
# ReviewItemFactory
# ---------------------------------------------------------------------------

class TestReviewItemFactory:
    def test_creates_review_item_on_name_match_with_iban(self):
        """ADR-012: ReviewItem created when name_match + raw IBAN present."""
        from app.imports.matching import PartnerMatchResult
        result = PartnerMatchResult(
            partner_id=uuid4(),
            outcome=MatchOutcome.name_match,
            review_context={"matched_on": "name"},
        )
        line = _make_journal_line(iban_raw="DE89370400440532013000", name_raw="Amazon EU")
        mandant_id = uuid4()

        ri = ReviewItemFactory.maybe_create(result, line, mandant_id)

        assert ri is not None
        assert ri.item_type == "name_match_with_iban"
        assert ri.journal_line_id == line.id
        assert ri.mandant_id == mandant_id
        assert ri.status == "open"
        assert ri.context == {"matched_on": "name"}

    def test_no_review_item_on_name_match_without_iban(self):
        """ADR-012: no ReviewItem when name_match but no raw IBAN (already expected)."""
        from app.imports.matching import PartnerMatchResult
        result = PartnerMatchResult(
            partner_id=uuid4(),
            outcome=MatchOutcome.name_match,
            review_context={"matched_on": "name"},
        )
        line = _make_journal_line(iban_raw=None, name_raw="Some Name")

        ri = ReviewItemFactory.maybe_create(result, line, uuid4())

        assert ri is None

    def test_no_review_item_on_iban_match(self):
        """IBAN match is unambiguous — no review needed."""
        from app.imports.matching import PartnerMatchResult
        result = PartnerMatchResult(partner_id=uuid4(), outcome=MatchOutcome.iban_match)
        line = _make_journal_line(iban_raw="DE89370400440532013000", name_raw="Amazon EU")

        ri = ReviewItemFactory.maybe_create(result, line, uuid4())

        assert ri is None

    def test_no_review_item_on_new_partner(self):
        """New partner = auto-created, no ambiguity → no review needed."""
        from app.imports.matching import PartnerMatchResult
        result = PartnerMatchResult(partner_id=uuid4(), outcome=MatchOutcome.new_partner)
        line = _make_journal_line(iban_raw="DE89370400440532013000", name_raw="Brand New")

        ri = ReviewItemFactory.maybe_create(result, line, uuid4())

        assert ri is None
