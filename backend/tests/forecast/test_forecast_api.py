"""Regel-Verwaltung, Planposten, Übersicht und Szenarien über die API."""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelSession

from app.auth.models import UserRole
from app.forecast.rules import Scenario
from app.journal.service import JournalService
from app.services.models import ServiceType
from tests.forecast.test_matrix_forecast import (
    TODAY,
    book,
    cells_of,
    create_service_db,
    setup_salary,
)
from tests.journal import create_user, get_auth_token


async def auth(client: AsyncClient, user, mandant) -> dict[str, str]:
    token = await get_auth_token(client, user, mandant)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestRuleEndpoint:
    async def test_zeigt_erkannte_regel_und_vorschau(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "auto"
        assert body["detected_rule_type"] == "fixed_recurring"
        assert body["effective_rule_type"] == "fixed_recurring"
        assert body["confidence"] == "high"
        assert len(body["preview"]) == 12
        assert body["preview"][0]["period"] == "2026-09"

    async def test_haendische_regel_wird_gespeichert_und_wirksam(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={
                "mode": "manual",
                "rule_type": "fixed_recurring",
                "params": {"amount": "-4000"},
                "adjustment_pct": "0",
                "shift_months": 0,
            },
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["mode"] == "manual"

        matrix = await JournalService(
            db_session, today=TODAY
        ).get_income_expense_matrix(mandant_id=mandant.id, year=2027)
        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["jan"]["gross"] == "-4000.00"
        assert row["forecast_mode"] == "manual"

    async def test_abschalten_entfernt_die_leistung_aus_der_prognose(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={"mode": "off"},
            headers=headers,
        )

        matrix = await JournalService(
            db_session, today=TODAY
        ).get_income_expense_matrix(mandant_id=mandant.id, year=2027)
        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["jan"]["gross"] == "0.00"
        assert row["forecast_mode"] == "off"

    async def test_indexierung_wirkt_auch_im_automatikmodus(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={"mode": "auto", "adjustment_pct": "3.00"},
            headers=headers,
        )

        matrix = await JournalService(
            db_session, today=TODAY
        ).get_income_expense_matrix(mandant_id=mandant.id, year=2027)
        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["jan"]["gross"] == "-3090.00"

    async def test_zuruecksetzen_stellt_den_vorschlag_wieder_her(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        url = f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule"
        await client.put(url, json={"mode": "off"}, headers=headers)

        resp = await client.delete(url, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["mode"] == "auto"
        assert resp.json()["effective_rule_type"] == "fixed_recurring"

    async def test_manual_ohne_regeltyp_wird_abgelehnt(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={"mode": "manual"},
            headers=headers,
        )

        assert resp.status_code == 422

    async def test_viewer_darf_nicht_schreiben(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        _, mandant, _, _, _, service = await setup_salary(db_session)
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        from tests.journal import assign_user_to_mandant

        await assign_user_to_mandant(db_session, viewer, mandant)
        headers = await auth(client, viewer, mandant)

        resp = await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={"mode": "off"},
            headers=headers,
        )

        assert resp.status_code == 403

    async def test_fremde_leistung_ergibt_404(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        from uuid import uuid4

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/services/{uuid4()}/forecast-rule",
            headers=headers,
        )

        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPlannedItems:
    async def test_planposten_ersetzt_die_schaetzung(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
            json={
                "service_id": str(service.id),
                "period": "2027-04",
                "amount": "-9999.00",
                "note": "Abfertigung",
            },
            headers=headers,
        )

        assert resp.status_code == 201
        matrix = await JournalService(
            db_session, today=TODAY
        ).get_income_expense_matrix(mandant_id=mandant.id, year=2027)
        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["apr"]["gross"] == "-9999.00"
        assert row["cells"]["mar"]["gross"] == "-3000.00"

    async def test_planposten_bleibt_vom_szenario_unberuehrt(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
            json={
                "service_id": str(service.id),
                "period": "2027-04",
                "amount": "-9999.00",
            },
            headers=headers,
        )

        matrix = await JournalService(
            db_session, today=TODAY
        ).get_income_expense_matrix(
            mandant_id=mandant.id, year=2027, scenario=Scenario.low
        )

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["apr"]["gross"] == "-9999.00"
        # Der geschätzte Nachbarmonat bewegt sich sehr wohl.
        assert row["cells"]["mar"]["gross"] == "-3150.00"

    async def test_mehrere_posten_im_selben_monat_summieren_sich(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        for amount in ("-1000.00", "-500.00"):
            await client.post(
                f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
                json={
                    "service_id": str(service.id),
                    "period": "2027-05",
                    "amount": amount,
                },
                headers=headers,
            )

        matrix = await JournalService(
            db_session, today=TODAY
        ).get_income_expense_matrix(mandant_id=mandant.id, year=2027)

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["may"]["gross"] == "-1500.00"

    async def test_auflisten_aendern_und_loeschen(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        base = f"/api/v1/mandants/{mandant.id}/forecast/planned-items"
        created = await client.post(
            base,
            json={
                "service_id": str(service.id),
                "period": "2027-04",
                "amount": "-100.00",
            },
            headers=headers,
        )
        item_id = created.json()["id"]

        listed = await client.get(base, headers=headers)
        assert len(listed.json()) == 1
        assert listed.json()[0]["service_name"] == "Gehalt"

        patched = await client.patch(
            f"{base}/{item_id}", json={"amount": "-250.00"}, headers=headers
        )
        assert Decimal(patched.json()["amount"]) == Decimal("-250.00")

        deleted = await client.delete(f"{base}/{item_id}", headers=headers)
        assert deleted.status_code == 204
        assert (await client.get(base, headers=headers)).json() == []

    async def test_ungueltige_periode_wird_abgelehnt(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
            json={
                "service_id": str(service.id),
                "period": "2027-13",
                "amount": "-100.00",
            },
            headers=headers,
        )

        assert resp.status_code == 422


@pytest.mark.asyncio
class TestOverview:
    async def test_listet_leistungen_mit_regel_und_relevanz(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, account, run, partner, _ = await setup_salary(db_session)
        sporadic = await create_service_db(
            db_session, partner.id, "Projekt X", ServiceType.customer
        )
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=sporadic.id,
            valuta_date="2026-07-10",
            amount="20000.00",
        )
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/services", headers=headers
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["without_rule"] == 1
        # Nach Relevanz sortiert: das Gehalt trägt die größere Summe.
        assert body["services"][0]["service_name"] == "Gehalt"
        assert body["services"][0]["effective_rule_type"] == "fixed_recurring"

    async def test_filtert_auf_leistungen_ohne_regel(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, account, run, partner, _ = await setup_salary(db_session)
        sporadic = await create_service_db(
            db_session, partner.id, "Projekt X", ServiceType.customer
        )
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=sporadic.id,
            valuta_date="2026-07-10",
            amount="20000.00",
        )
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/services?only_without_rule=true",
            headers=headers,
        )

        names = [row["service_name"] for row in resp.json()["services"]]
        assert names == ["Projekt X"]

    async def test_sucht_nach_name(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/services?search=gehal",
            headers=headers,
        )

        assert [row["service_name"] for row in resp.json()["services"]] == ["Gehalt"]


@pytest.mark.asyncio
class TestScenarios:
    async def test_pessimistisches_szenario_erhoeht_ausgaben(
        self, db_session: SQLModelSession
    ):
        _, mandant, *_ = await setup_salary(db_session)
        svc = JournalService(db_session, today=TODAY)

        expected = await svc.get_income_expense_matrix(mandant_id=mandant.id, year=2027)
        low = await svc.get_income_expense_matrix(
            mandant_id=mandant.id, year=2027, scenario=Scenario.low
        )

        assert (
            cells_of(expected.model_dump(), "Gehalt")["cells"]["jan"]["gross"]
            == "-3000.00"
        )
        # Das Gehalt ist im Rückvergleich exakt getroffen worden. Die Bandbreite ist
        # deshalb die gemessene Untergrenze von 5 %, nicht die geschätzten 10 % nach
        # Confidence — und sie wirkt nach unten auf den Saldo.
        assert (
            cells_of(low.model_dump(), "Gehalt")["cells"]["jan"]["gross"] == "-3150.00"
        )

    async def test_liquiditaet_faellt_im_pessimistischen_szenario_tiefer(
        self, db_session: SQLModelSession
    ):
        _, mandant, *_ = await setup_salary(db_session)
        svc = JournalService(db_session, today=TODAY)

        expected = await svc.get_liquidity(mandant.id)
        low = await svc.get_liquidity(mandant.id, scenario=Scenario.low)
        high = await svc.get_liquidity(mandant.id, scenario=Scenario.high)

        assert low.scenario == "low"
        assert Decimal(low.lowest_balance) < Decimal(expected.lowest_balance)
        assert Decimal(high.lowest_balance) > Decimal(expected.lowest_balance)

    async def test_szenario_ueber_http(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/reports/liquidity?scenario=high",
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["scenario"] == "high"

    async def test_unbekanntes_szenario_wird_abgelehnt(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/reports/liquidity?scenario=hoffnung",
            headers=headers,
        )

        assert resp.status_code == 422
