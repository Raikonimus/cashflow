"""Gruppierung und Auflösung nicht erkannter Partner (Kartenimporte)."""
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import JournalLine, JournalLineSplit, ReviewItem, utcnow
from app.partners.models import Partner, PartnerName
from app.review.service import merchant_key
from app.imports.matching import PartnerMatchingService
from app.services.models import Service, ServiceMatcher
from app.services.service import ensure_base_service

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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _unidentified(session: AsyncSession, mandant_id, text: str, amount: str, date: str = "2026-01-15"):
    now = utcnow()
    line = JournalLine(
        id=uuid4(), account_id=uuid4(), import_run_id=uuid4(), partner_id=None,
        valuta_date=date, booking_date=date, amount=Decimal(amount), currency="EUR",
        text=text, partner_name_raw=None, partner_iban_raw=None, created_at=now,
    )
    session.add(line)
    await session.flush()
    item = ReviewItem(
        mandant_id=mandant_id, item_type="no_partner_identified", journal_line_id=line.id,
        context={"raw_text": text}, status="open", created_at=now,
    )
    session.add(item)
    await session.flush()
    return line, item


class TestMerchantKey:
    @pytest.mark.parametrize(("text", "expected"), [
        ("ANTHROPIC inkl. Fremdwährungsentgelt 1,32 Kurs 1,1405109", "ANTHROPIC"),
        ("ANTHROPIC* CLAUDE SUB", "ANTHROPIC"),
        ("ANTHROPIC", "ANTHROPIC"),
        ("MSFT * E0301094XL", "MSFT"),
        ("GOOGLE*ADS6139956915", "GOOGLE"),
        ("DNH*GODADDY#4034891289", "GODADDY"),
        ("LinkedIn P3006756968", "LINKEDIN"),
        ("PARK & RIDE SPITTELAU", "PARK & RIDE SPITTELAU"),
        ("SUMUP * DEALGOOD GMBH", "DEALGOOD GMBH"),
        ("", ""),
        (None, ""),
    ])
    def test_merchant_key(self, text, expected):
        assert merchant_key(text) == expected

    def test_reine_zahlenzeile_wird_nicht_leer(self):
        # Der letzte Token bleibt stehen, wenn sonst nichts uebrig bliebe.
        assert merchant_key("12345") == ""


@pytest.mark.asyncio
class TestUnidentifiedGroups:
    async def test_gruppiert_nach_haendler_und_sortiert_nach_groesse(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp1@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        await _unidentified(db_session, mandant.id, "ANTHROPIC inkl. Fremdwährungsentgelt 1,32 Kurs 1,14", "-89.00", "2026-01-02")
        await _unidentified(db_session, mandant.id, "ANTHROPIC inkl. Fremdwährungsentgelt 1,18 Kurs 1,14", "-80.12", "2026-02-03")
        await _unidentified(db_session, mandant.id, "ANTHROPIC* CLAUDE SUB", "-149.21", "2026-03-04")
        await _unidentified(db_session, mandant.id, "MSFT * E0301094XL", "-22.50", "2026-01-20")
        await db_session.commit()

        resp = await client.get(f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()

        assert body["total_open"] == 4
        assert body["grouped"] == 4
        assert [g["key"] for g in body["groups"]] == ["ANTHROPIC", "MSFT"]

        anthropic = body["groups"][0]
        assert anthropic["line_count"] == 3
        assert Decimal(anthropic["total_amount"]) == Decimal("-318.33")
        assert anthropic["first_date"] == "2026-01-02"
        assert anthropic["last_date"] == "2026-03-04"
        assert anthropic["suggested_pattern"] == "ANTHROPIC"
        assert anthropic["suggested_partner_name"] == "Anthropic"
        assert len(anthropic["item_ids"]) == 3

        # Jede Buchungszeile einzeln, nach Valutadatum sortiert - auch wenn
        # sich Texte wiederholen.
        assert [line["valuta_date"] for line in anthropic["lines"]] == [
            "2026-01-02", "2026-02-03", "2026-03-04",
        ]
        assert [Decimal(line["amount"]) for line in anthropic["lines"]] == [
            Decimal("-89.00"), Decimal("-80.12"), Decimal("-149.21"),
        ]
        assert anthropic["lines"][2]["text"] == "ANTHROPIC* CLAUDE SUB"

    async def test_schlaegt_bestehenden_partner_statt_eines_duplikats_vor(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Echter Fall: Kern "WEAVIATE B.V" neben Partner "WEAVIATE B.V." ."""
        user = await create_user(db_session, "grp12@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "WEAVIATE B.V.")

        await _unidentified(
            db_session, mandant.id,
            "WEAVIATE B.V. inkl. Fremdwährungsentgelt 0,33 Kurs 1,1271415", "-22.51",
        )
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]
        assert group["key"] == "WEAVIATE B.V"
        assert group["suggested_partner_id"] == str(partner.id)
        # Nicht die verschoenerte Form "Weaviate B.V" - die wuerde ein Duplikat anlegen.
        assert group["suggested_partner_name"] == "WEAVIATE B.V."

    async def test_schlaegt_bei_mehreren_passenden_partnern_keinen_vor(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp13@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner_db(db_session, mandant.id, "EXOSCALE")
        await create_partner_db(db_session, mandant.id, "Exoscale")

        await _unidentified(db_session, mandant.id, "EXOSCALE", "-15.00")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]
        assert group["suggested_partner_id"] is None
        assert group["suggested_partner_name"] == "Exoscale"

    async def test_schlaegt_inaktive_partner_nicht_vor(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Matcher inaktiver Partner greifen nicht - ein Vorschlag waere eine Sackgasse."""
        user = await create_user(db_session, "grp14@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "OLLAMA")
        partner.is_active = False
        db_session.add(partner)

        await _unidentified(db_session, mandant.id, "OLLAMA", "-4.56")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]
        assert group["suggested_partner_id"] is None

    async def test_findet_den_partner_ueber_eine_namensvariante(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp15@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Google Ireland Ltd")
        db_session.add(PartnerName(
            id=uuid4(), partner_id=partner.id, name="google payment ie ltd", created_at=utcnow(),
        ))

        await _unidentified(db_session, mandant.id, "GOOGLE PAYMENT IE LTD", "-42.00")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]
        assert group["suggested_partner_id"] == str(partner.id)
        assert group["suggested_partner_name"] == "Google Ireland Ltd"

    async def test_partnername_wird_ohne_ruecksicht_auf_schreibweise_wiederverwendet(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Sicherheitsnetz: uq_partners_mandant_name unterscheidet Gross-/Kleinschreibung."""
        user = await create_user(db_session, "grp16@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "ANTHROPIC")

        _, item = await _unidentified(db_session, mandant.id, "ANTHROPIC* CLAUDE SUB", "-99.58")
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={"item_ids": [str(item.id)], "pattern": "ANTHROPIC",
                  "service_name": "Claude", "partner_name": "Anthropic"},
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["partner_id"] == str(partner.id)

        partners = (await db_session.exec(select(Partner).where(Partner.mandant_id == mandant.id))).all()
        assert [p.name for p in partners] == ["ANTHROPIC"]

    async def test_legt_partner_leistung_matcher_an_und_ordnet_alle_zeilen_zu(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        lines = [
            (await _unidentified(db_session, mandant.id, "ANTHROPIC inkl. Fremdwährungsentgelt 1,32", "-89.00"))[0],
            (await _unidentified(db_session, mandant.id, "ANTHROPIC* CLAUDE SUB", "-149.21"))[0],
        ]
        await db_session.commit()

        groups = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"]
        group = groups[0]

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": group["item_ids"],
                "pattern": group["suggested_pattern"],
                "service_name": "Claude",
                "partner_name": group["suggested_partner_name"],
            },
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        result = resp.json()
        assert result["partner_name"] == "Anthropic"
        assert result["resolved_items"] == 2
        assert result["assigned_lines"] == 2

        partner = await db_session.get(Partner, __import__("uuid").UUID(result["partner_id"]))
        assert partner is not None and partner.name == "Anthropic"

        service = await db_session.get(Service, __import__("uuid").UUID(result["service_id"]))
        assert service.name == "Claude"
        # Art bleibt automatisch, damit die Erkennung sie bestimmen kann.
        assert service.service_type_manual is False
        assert service.tax_rate_manual is False

        matcher = await db_session.get(ServiceMatcher, __import__("uuid").UUID(result["matcher_id"]))
        assert matcher.pattern == "ANTHROPIC"
        assert matcher.internal_only is False

        # Beide Zeilen haengen jetzt am Partner und sind der Leistung zugeordnet.
        for line in lines:
            await db_session.refresh(line)
            assert line.partner_id == partner.id
            splits = (await db_session.exec(
                select(JournalLineSplit).where(JournalLineSplit.journal_line_id == line.id))).all()
            assert [sp.service_id for sp in splits] == [service.id]

        # Die Review-Items sind erledigt und die Gruppe verschwindet aus der Liste.
        items = (await db_session.exec(
            select(ReviewItem).where(ReviewItem.item_type == "no_partner_identified"))).all()
        assert {i.status for i in items} == {"adjusted"}
        after = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()
        assert after["groups"] == []

    async def test_nutzt_bestehenden_partner_statt_neu_anzulegen(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp3@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Microsoft")

        await _unidentified(db_session, mandant.id, "MSFT * E0301094XL", "-22.50")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": group["item_ids"], "pattern": "MSFT",
                "service_name": "Lizenzen", "partner_id": str(partner.id),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["partner_id"] == str(partner.id)

        partners = (await db_session.exec(select(Partner).where(Partner.mandant_id == mandant.id))).all()
        assert [p.name for p in partners] == ["Microsoft"]

    async def test_haengt_matcher_an_bestehende_leistung_des_partners(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp6@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Microsoft")
        service = Service(
            id=uuid4(), partner_id=partner.id, name="Lizenzen",
            service_type="supplier", tax_rate=Decimal("20.00"),
            created_at=utcnow(), updated_at=utcnow(),
        )
        db_session.add(service)
        await db_session.flush()

        line, _ = await _unidentified(db_session, mandant.id, "MSFT * E0301094XL", "-22.50")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": group["item_ids"], "pattern": "MSFT",
                "partner_id": str(partner.id), "service_id": str(service.id),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["service_id"] == str(service.id)

        # Keine zusaetzliche Leistung neben Basisleistung und der gewaehlten.
        services = (await db_session.exec(
            select(Service).where(Service.partner_id == partner.id))).all()
        assert sorted(s.name for s in services) == ["Basisleistung", "Lizenzen"]
        matchers = (await db_session.exec(
            select(ServiceMatcher).where(ServiceMatcher.service_id == service.id))).all()
        assert [m.pattern for m in matchers] == ["MSFT"]

        await db_session.refresh(line)
        assert line.partner_id == partner.id

    async def test_folgeimport_findet_den_abweichend_benannten_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Der Matcher haengt an der Leistung - der Partnername spielt keine Rolle."""
        user = await create_user(db_session, "grp10@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Google Ireland Ltd")

        await _unidentified(db_session, mandant.id, "GOOGLE*ADS6139956915", "-120.00")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]
        assert group["key"] == "GOOGLE"
        # Der Vorschlag lautet "Google" - zugeordnet wird trotzdem "Google Ireland Ltd".
        assert group["suggested_partner_name"] == "Google"

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": group["item_ids"], "pattern": "GOOGLE",
                "partner_id": str(partner.id), "service_name": "Google Ads",
            },
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        await db_session.commit()

        # Folgeimport derselben Buchung: Kartenzeilen tragen weder IBAN noch
        # Partnername, es bleibt allein der Leistungs-Matcher.
        result = await PartnerMatchingService(db_session).match(
            mandant_id=mandant.id, iban_raw=None, name_raw=None,
            text_raw="GOOGLE*ADS7000000001",
        )
        assert result.outcome.value == "service_matcher_match"
        assert result.partner_id == partner.id

    async def test_lehnt_matcher_an_der_basisleistung_ab(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Partnererkennung und Leistungszuordnung ueberspringen Basisleistungen."""
        user = await create_user(db_session, "grp11@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Google Ireland Ltd")
        base = await ensure_base_service(db_session, partner.id)

        _, item = await _unidentified(db_session, mandant.id, "GOOGLE*ADS6139956915", "-120.00")
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": [str(item.id)], "pattern": "GOOGLE",
                "partner_id": str(partner.id), "service_id": str(base.id),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 422
        assert "Basisleistung" in resp.json()["detail"]

    async def test_lehnt_leistung_eines_fremden_partners_ab(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp7@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Microsoft")
        other = await create_partner_db(db_session, mandant.id, "Anthropic")
        foreign = Service(
            id=uuid4(), partner_id=other.id, name="Claude",
            service_type="supplier", tax_rate=Decimal("20.00"),
            created_at=utcnow(), updated_at=utcnow(),
        )
        db_session.add(foreign)
        _, item = await _unidentified(db_session, mandant.id, "MSFT * E0301094XL", "-22.50")
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": [str(item.id)], "pattern": "MSFT",
                "partner_id": str(partner.id), "service_id": str(foreign.id),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_verlangt_service_id_oder_service_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp8@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        _, item = await _unidentified(db_session, mandant.id, "OLLAMA", "-4.56")
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={"item_ids": [str(item.id)], "pattern": "OLLAMA", "partner_name": "Ollama"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_gleicher_leistungsname_legt_keine_zweite_leistung_an(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp9@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "Microsoft")

        _, first = await _unidentified(db_session, mandant.id, "MSFT * E0301094XL", "-22.50")
        _, second = await _unidentified(db_session, mandant.id, "MSFT * E0300ZSOSD", "-11.00", "2026-02-15")
        await db_session.commit()

        for item, pattern in ((first, "MSFT *"), (second, "MSFT")):
            resp = await client.post(
                f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
                json={
                    "item_ids": [str(item.id)], "pattern": pattern,
                    "partner_id": str(partner.id), "service_name": "Lizenzen",
                },
                headers=_auth(token),
            )
            assert resp.status_code == 201, resp.text

        services = (await db_session.exec(
            select(Service).where(Service.partner_id == partner.id, Service.name == "Lizenzen"))).all()
        assert len(services) == 1

    async def test_mehrdeutige_leistung_landet_auf_der_basisleistung(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Echter Fall: zwei Matcher desselben Partners treffen dieselbe Zeile.

        Die Bank kuerzt den Haendlernamen unterschiedlich ab, daraus entstehen
        zwei Leistungen mit ueberlappenden Mustern. Die Zeile darf dabei nicht
        ohne Zuordnung zurueckbleiben - sonst faellt sie aus Einnahmen &
        Ausgaben heraus und die Bestaetigung scheitert an der Zielleistung.
        """
        user = await create_user(db_session, "grp17@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner_db(db_session, mandant.id, "HF Data")
        base = await ensure_base_service(db_session, partner.id)
        kurz = Service(
            id=uuid4(), partner_id=partner.id, name="HF Data Datenve",
            service_type="supplier", tax_rate=Decimal("20.00"),
            created_at=utcnow(), updated_at=utcnow(),
        )
        db_session.add(kurz)
        await db_session.flush()
        db_session.add(ServiceMatcher(
            id=uuid4(), service_id=kurz.id, pattern="HF DATA DATENVE",
            pattern_type="string", internal_only=False, created_at=utcnow(),
        ))

        line, _ = await _unidentified(db_session, mandant.id, "Mol*HF Data Datenverar...", "-14.90")
        await db_session.commit()

        group = (await client.get(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups", headers=_auth(token))).json()["groups"][0]
        assert group["key"] == "HF DATA DATENVERAR"

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={
                "item_ids": group["item_ids"], "pattern": "HF DATA DATENVERAR",
                "partner_id": str(partner.id), "service_name": "HF Data Datenverar",
            },
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text

        # Beide Muster treffen - die Zeile haengt trotzdem an genau einer Leistung.
        splits = (await db_session.exec(
            select(JournalLineSplit).where(JournalLineSplit.journal_line_id == line.id))).all()
        assert [sp.service_id for sp in splits] == [base.id]

        review = (await db_session.exec(select(ReviewItem).where(
            ReviewItem.item_type == "service_assignment", ReviewItem.status == "open"))).first()
        assert review is not None
        assert review.context["reason"] == "multiple_matches"
        assert review.context["current_service_id"] == str(base.id)

        # Und laesst sich bestaetigen, statt an einer fehlenden Zielleistung zu scheitern.
        confirmed = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/{review.id}/confirm", headers=_auth(token))
        assert confirmed.status_code == 200, confirmed.text

    async def test_lehnt_leere_oder_bereits_erledigte_gruppe_ab(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp4@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)

        _, item = await _unidentified(db_session, mandant.id, "OLLAMA", "-4.56")
        item.status = "adjusted"
        db_session.add(item)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={"item_ids": [str(item.id)], "pattern": "OLLAMA",
                  "service_name": "Ollama", "partner_name": "Ollama"},
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_verlangt_partner_id_oder_partner_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "grp5@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        _, item = await _unidentified(db_session, mandant.id, "OLLAMA", "-4.56")
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/review/unidentified-groups/resolve",
            json={"item_ids": [str(item.id)], "pattern": "OLLAMA", "service_name": "Ollama"},
            headers=_auth(token),
        )
        assert resp.status_code == 422
