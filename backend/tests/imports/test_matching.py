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
        """ADR-011: inactive partners must never be matched by IBAN.

        Wenn die IBAN zu einem inaktiven Partner gehört und ein Partnername bekannt ist,
        muss ein neuer Partner angelegt werden (new_partner), nicht iban_match zurückgegeben.
        Ohne Partnernamen ist das Ergebnis no_partner_identified – ebenfalls kein iban_match.
        """
        mandant = await create_mandant(db_session)
        await _create_inactive_partner(
            db_session, mandant.id, "Old Corp", iban="DE89370400440532013000"
        )

        svc = PartnerMatchingService(db_session)

        # Mit Partnername → neuer Partner angelegt
        result_with_name = await svc.match(
            mandant_id=mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw="New Corp",
        )
        assert result_with_name.outcome == MatchOutcome.new_partner

        # Ohne Partnername → kein Partner identifizierbar, aber immer noch kein iban_match
        result_no_name = await svc.match(
            mandant_id=mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw=None,
        )
        assert result_no_name.outcome == MatchOutcome.no_partner_identified
        assert result_no_name.outcome != MatchOutcome.iban_match

    async def test_iban_not_matched_across_mandants(self, db_session: AsyncSession):
        """An IBAN registered under another mandant must not match."""
        other_mandant = await create_mandant(db_session, "Other GmbH")
        await _create_active_partner(
            db_session, other_mandant.id, "Fremdfirma", iban="DE89370400440532013000"
        )

        own_mandant = await create_mandant(db_session, "Own AG")
        svc = PartnerMatchingService(db_session)

        # Mit Namen → neuer Partner für eigenen Mandanten
        result = await svc.match(
            mandant_id=own_mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw="Fremdfirma Kopie",
        )
        assert result.outcome == MatchOutcome.new_partner

        # Ohne Namen → kein Partner identifizierbar, kein Cross-Mandant-Match
        result_no_name = await svc.match(
            mandant_id=own_mandant.id,
            iban_raw="DE89370400440532013000",
            name_raw=None,
        )
        assert result_no_name.outcome == MatchOutcome.no_partner_identified


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

    async def test_iban_not_found_falls_back_to_name(self, db_session: AsyncSession):
        """Wenn eine IBAN übergeben wird, aber kein Partner damit gefunden wird,
        muss der Partnername als Fallback geprüft werden."""
        mandant = await create_mandant(db_session)
        partner = await _create_active_partner(
            db_session, mandant.id, "Bekannter Partner", alias="Bekannter Partner"
        )

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="AT611904300234573201",   # unbekannte IBAN
            name_raw="Bekannter Partner",
        )

        assert result.outcome == MatchOutcome.name_match
        assert result.partner_id == partner.id

    async def test_name_match_on_partner_name_without_alias(self, db_session: AsyncSession):
        """Partner der manuell (ohne PartnerName-Eintrag) angelegt wurde, muss
        über partners.name gefunden werden – nicht nur über partner_names."""
        mandant = await create_mandant(db_session)
        # Kein alias → kein PartnerName-Eintrag, nur partners.name
        partner = await _create_active_partner(db_session, mandant.id, "Erste Bank")

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw="Erste Bank",
        )

        assert result.outcome == MatchOutcome.name_match
        assert result.partner_id == partner.id

    async def test_iban_not_found_falls_back_to_partner_name_without_alias(self, db_session: AsyncSession):
        """Kombination: IBAN unbekannt + Partner nur mit partners.name (kein PartnerName-Eintrag)."""
        mandant = await create_mandant(db_session)
        partner = await _create_active_partner(db_session, mandant.id, "Sparkasse Wien")

        svc = PartnerMatchingService(db_session)
        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="AT611904300234573201",   # unbekannte IBAN
            name_raw="Sparkasse Wien",
        )

        assert result.outcome == MatchOutcome.name_match
        assert result.partner_id == partner.id


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

    async def test_no_name_no_iban_creates_no_partner(self, db_session: AsyncSession):
        """Ohne Partnername und ohne IBAN kann kein neuer Partner angelegt werden."""
        mandant = await create_mandant(db_session)

        svc = PartnerMatchingService(db_session)
        result = await svc.match(mandant_id=mandant.id, iban_raw=None, name_raw=None)

        assert result.outcome == MatchOutcome.no_partner_identified
        assert result.partner_id is None


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

    def test_review_item_created_on_new_partner(self):
        """Automatisch angelegter neuer Partner erzeugt einen new_partner ReviewItem."""
        from app.imports.matching import PartnerMatchResult
        new_pid = uuid4()
        result = PartnerMatchResult(partner_id=new_pid, outcome=MatchOutcome.new_partner)
        line = _make_journal_line(iban_raw=None, name_raw="Brand New")
        mandant_id = uuid4()

        ri = ReviewItemFactory.maybe_create(result, line, mandant_id)

        assert ri is not None
        assert ri.item_type == "new_partner"
        assert ri.journal_line_id == line.id
        assert ri.mandant_id == mandant_id
        assert ri.status == "open"
        assert ri.context["partner_name_raw"] == "Brand New"
        assert ri.context["new_partner_id"] == str(new_pid)


# ---------------------------------------------------------------------------
# no_partner_identified — Diagnose im review_context
# ---------------------------------------------------------------------------

class TestNoPartnerDiagnosis:
    async def test_diagnosis_no_iban_no_account_no_name(self, db_session: AsyncSession):
        """Kein Input → Diagnose zeigt alle Felder als 'nicht vorhanden'."""
        mandant = await create_mandant(db_session)
        svc = PartnerMatchingService(db_session)

        result = await svc.match(mandant_id=mandant.id, iban_raw=None, name_raw=None)

        assert result.outcome == MatchOutcome.no_partner_identified
        diag = result.review_context["diagnosis"]
        assert diag["iban"] == {"provided": False}
        assert diag["account"] == {"provided": False}
        assert diag["name"] == {"provided": False}

    async def test_diagnosis_iban_provided_but_not_found(self, db_session: AsyncSession):
        """IBAN vorhanden, aber kein Partner – Diagnose zeigt found=False."""
        mandant = await create_mandant(db_session)
        svc = PartnerMatchingService(db_session)

        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="AT61 1904 3002 3457 3201",
            name_raw=None,
        )

        assert result.outcome == MatchOutcome.no_partner_identified
        iban_diag = result.review_context["diagnosis"]["iban"]
        assert iban_diag["provided"] is True
        assert iban_diag["excluded"] is False
        assert iban_diag["found"] is False
        assert iban_diag["normalized"] == "AT611904300234573201"

    async def test_diagnosis_iban_excluded(self, db_session: AsyncSession):
        """Eigene IBAN ausgeschlossen – Diagnose zeigt excluded=True."""
        mandant = await create_mandant(db_session)
        svc = PartnerMatchingService(db_session)

        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw="AT611904300234573201",
            name_raw=None,
            excluded_ibans=frozenset({"AT611904300234573201"}),
        )

        assert result.outcome == MatchOutcome.no_partner_identified
        iban_diag = result.review_context["diagnosis"]["iban"]
        assert iban_diag["provided"] is True
        assert iban_diag["excluded"] is True

    async def test_diagnosis_service_matchers_no_text(self, db_session: AsyncSession):
        """Kein Buchungstext → Leistungs-Matcher nicht geprüft."""
        mandant = await create_mandant(db_session)
        svc = PartnerMatchingService(db_session)

        result = await svc.match(mandant_id=mandant.id, iban_raw=None, name_raw=None, text_raw=None)

        assert result.outcome == MatchOutcome.no_partner_identified
        sm_diag = result.review_context["diagnosis"]["service_matchers"]
        assert sm_diag["skipped"] is True
        assert sm_diag["reason"] == "no_searchable_text"

    async def test_diagnosis_service_matchers_no_match(self, db_session: AsyncSession):
        """Buchungstext vorhanden, aber kein Matcher trifft."""
        mandant = await create_mandant(db_session)
        svc = PartnerMatchingService(db_session)

        result = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw=None,
            text_raw="Unbekannte Buchung ohne Treffer",
        )

        assert result.outcome == MatchOutcome.no_partner_identified
        sm_diag = result.review_context["diagnosis"]["service_matchers"]
        # Keine Matcher konfiguriert → skipped=False, total_matchers=0
        assert sm_diag["skipped"] is False
        assert sm_diag["total_matchers"] == 0
