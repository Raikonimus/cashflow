"""internal_only-Matcher dienen der Leistungswahl innerhalb eines bekannten
Partners und dürfen den Partner nicht identifizieren."""
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.matching import PartnerMatchingService
from app.imports.models import utcnow
from app.services.models import Service, ServiceMatcher, ServiceMatcherType

from tests.imports import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_mandant,
    create_partner_db,
    create_user,
    db_session,
    setup_db,
)


async def _matcher(session: AsyncSession, mandant_id, partner_name: str, pattern: str, internal_only: bool):
    partner = await create_partner_db(session, mandant_id, partner_name)
    service = Service(
        id=uuid4(), partner_id=partner.id, name=f"{partner_name} Leistung",
        created_at=utcnow(), updated_at=utcnow(),
    )
    session.add(service)
    await session.flush()
    session.add(ServiceMatcher(
        id=uuid4(), service_id=service.id, pattern=pattern,
        pattern_type=ServiceMatcherType.string.value, internal_only=internal_only,
        created_at=utcnow(),
    ))
    await session.flush()
    return partner


@pytest.mark.asyncio
class TestInternalOnlyMatchers:
    async def test_interner_matcher_identifiziert_keinen_partner(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)
        # Echter Fall: das interne Muster "Rate" steckt in "PARKGARAGE PRATERSTERN".
        await _matcher(db_session, mandant.id, "Forschungsförderung", "Rate", internal_only=True)
        await db_session.flush()

        result = await PartnerMatchingService(db_session).match(
            mandant_id=mandant.id, iban_raw=None, name_raw=None, text_raw="PARKGARAGE PRATERSTERN",
        )
        assert result.outcome.value == "no_partner_identified"
        assert result.partner_id is None

    async def test_oeffentlicher_matcher_identifiziert_weiterhin(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)
        partner = await _matcher(db_session, mandant.id, "OpenAI", "OPENAI", internal_only=False)
        await db_session.flush()

        result = await PartnerMatchingService(db_session).match(
            mandant_id=mandant.id, iban_raw=None, name_raw=None, text_raw="OPENAI * CHATGPT SUBSCR",
        )
        assert result.outcome.value == "service_matcher_match"
        assert result.partner_id == partner.id

    async def test_interner_matcher_erzeugt_keine_mehrdeutigkeit(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)
        wanted = await _matcher(db_session, mandant.id, "OpenAI", "OPENAI", internal_only=False)
        await _matcher(db_session, mandant.id, "Störer", "CHATGPT", internal_only=True)
        await db_session.flush()

        result = await PartnerMatchingService(db_session).match(
            mandant_id=mandant.id, iban_raw=None, name_raw=None, text_raw="OPENAI * CHATGPT SUBSCR",
        )
        # Ohne den Filter waeren es zwei Kandidaten -> service_matcher_ambiguous.
        assert result.outcome.value == "service_matcher_match"
        assert result.partner_id == wanted.id

    async def test_partner_nur_mit_internen_matchern_bleibt_unsichtbar(self, db_session: AsyncSession):
        mandant = await create_mandant(db_session)
        await _matcher(db_session, mandant.id, "Nur intern", "CAL 100", internal_only=True)
        await db_session.flush()

        result = await PartnerMatchingService(db_session).match(
            mandant_id=mandant.id, iban_raw=None, name_raw=None, text_raw="CAL 100-26.003",
        )
        assert result.outcome.value == "no_partner_identified"
        assert result.review_context["diagnosis"]["service_matchers"]["reason"] == "no_matchers_configured"
