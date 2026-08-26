"""Gruppierung und Auflösung nicht erkannter Partner (Kartenimporte)."""
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import JournalLine, JournalLineSplit, ReviewItem, utcnow
from app.partners.models import Partner
from app.review.service import merchant_key
from app.services.models import Service, ServiceMatcher

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
        # Beispieltexte zeigen die Varianten, hoechstens drei.
        assert len(anthropic["sample_texts"]) == 3

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
