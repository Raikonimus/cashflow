"""Kennungen, die in einem Import auf fast jeder Zeile stehen, duerfen keinen
Partner anreichern - sonst zieht die Kontonummer-Suche alle Folgezeilen dorthin."""

from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.matching import PartnerMatchingService, _normalize_account
from app.imports.models import utcnow
from app.imports.service import _ubiquitous_values
from app.partners.models import Partner, PartnerAccount
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

CARD_ACCOUNT = "40005190700"


class TestUbiquitousValues:
    def _rows(self, values: list[str | None]) -> list[dict]:
        return [{"partner_account_raw": value} for value in values]

    def test_erkennt_die_ueberall_stehende_kennung(self):
        rows = self._rows([CARD_ACCOUNT] * 19 + ["40005191900"])
        assert _ubiquitous_values(
            rows, "partner_account_raw", _normalize_account
        ) == frozenset({CARD_ACCOUNT})

    def test_ignoriert_normale_streuung(self):
        # Haeufigste Kennung bei 40 % - so sehen echte Kontoauszuege aus.
        rows = self._rows([f"KONTO{i % 5}" for i in range(20)] + [CARD_ACCOUNT] * 8)
        assert (
            _ubiquitous_values(rows, "partner_account_raw", _normalize_account)
            == frozenset()
        )

    def test_greift_erst_ab_genug_zeilen(self):
        # Neun gleiche Zeilen sind kein belastbarer Anteil.
        assert (
            _ubiquitous_values(
                self._rows([CARD_ACCOUNT] * 9),
                "partner_account_raw",
                _normalize_account,
            )
            == frozenset()
        )
        assert _ubiquitous_values(
            self._rows([CARD_ACCOUNT] * 10), "partner_account_raw", _normalize_account
        ) == frozenset({CARD_ACCOUNT})

    def test_leere_werte_zaehlen_nicht_mit(self):
        rows = self._rows([None, "", *[CARD_ACCOUNT] * 18])
        assert _ubiquitous_values(
            rows, "partner_account_raw", _normalize_account
        ) == frozenset({CARD_ACCOUNT})


@pytest.mark.asyncio
class TestNoEnrichCascade:
    async def _partner_with_matcher(
        self, session: AsyncSession, mandant_id, name: str, pattern: str
    ) -> Partner:
        partner = await create_partner_db(session, mandant_id, name)
        service = Service(
            id=uuid4(),
            partner_id=partner.id,
            name=f"{name} Leistung",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(service)
        await session.flush()
        session.add(
            ServiceMatcher(
                id=uuid4(),
                service_id=service.id,
                pattern=pattern,
                pattern_type=ServiceMatcherType.string.value,
                internal_only=False,
                created_at=utcnow(),
            )
        )
        await session.flush()
        return partner

    async def test_ohne_schutz_zieht_die_kennung_alle_folgezeilen_mit(
        self, db_session: AsyncSession
    ):
        mandant = await create_mandant(db_session)
        await self._partner_with_matcher(db_session, mandant.id, "OpenAI", "OPENAI")
        await db_session.flush()
        svc = PartnerMatchingService(db_session)

        first = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw=None,
            account_raw=CARD_ACCOUNT,
            blz_raw="20111",
            text_raw="OPENAI * CHATGPT SUBSCR",
        )
        assert first.outcome.value == "service_matcher_match"
        await db_session.flush()

        # Ohne Schutz haengt die Kartennummer jetzt an OpenAI.
        second = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw=None,
            account_raw=CARD_ACCOUNT,
            blz_raw="20111",
            text_raw="Cafe Landtmann",
        )
        assert second.outcome.value == "account_match"
        assert second.partner_id == first.partner_id

    async def test_mit_schutz_bleibt_die_folgezeile_offen(
        self, db_session: AsyncSession
    ):
        mandant = await create_mandant(db_session)
        await self._partner_with_matcher(db_session, mandant.id, "OpenAI", "OPENAI")
        await db_session.flush()
        svc = PartnerMatchingService(db_session)
        no_enrich = frozenset({CARD_ACCOUNT})

        first = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw=None,
            account_raw=CARD_ACCOUNT,
            blz_raw="20111",
            text_raw="OPENAI * CHATGPT SUBSCR",
            no_enrich_accounts=no_enrich,
        )
        assert first.outcome.value == "service_matcher_match"
        await db_session.flush()

        # Die Kennung wurde nicht angehaengt ...
        accounts = (
            await db_session.exec(
                select(PartnerAccount).where(
                    PartnerAccount.account_number == CARD_ACCOUNT
                )
            )
        ).all()
        assert accounts == []

        # ... also faellt die naechste Zeile korrekt in die Review-Queue.
        second = await svc.match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw=None,
            account_raw=CARD_ACCOUNT,
            blz_raw="20111",
            text_raw="Cafe Landtmann",
            no_enrich_accounts=no_enrich,
        )
        assert second.outcome.value == "no_partner_identified"
        assert second.partner_id is None

    async def test_bereits_registrierte_kennung_trifft_weiterhin(
        self, db_session: AsyncSession
    ):
        """Die Erste-Bank-Gebuehrendatei: dieselbe Kennung auf jeder Zeile, aber bewusst
        registriert. Die Suche muss weiter greifen, nur die Anreicherung entfaellt."""
        mandant = await create_mandant(db_session)
        partner = await create_partner_db(db_session, mandant.id, "Erste Bank")
        db_session.add(
            PartnerAccount(
                partner_id=partner.id,
                blz="20111",
                account_number="49900997173",
                created_at=utcnow(),
            )
        )
        await db_session.flush()

        result = await PartnerMatchingService(db_session).match(
            mandant_id=mandant.id,
            iban_raw=None,
            name_raw=None,
            account_raw="49900997173",
            blz_raw="20111",
            text_raw="Kontoführung",
            no_enrich_accounts=frozenset({"49900997173"}),
        )
        assert result.outcome.value == "account_match"
        assert result.partner_id == partner.id
