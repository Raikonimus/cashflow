"""Rückvergleich und Plan-Ist-Snapshots über die API."""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelSession

from app.forecast.rules import Scenario
from app.forecast.schemas import CreateSnapshotRequest
from app.forecast.service import ForecastService
from app.journal.service import JournalService
from tests.forecast.test_forecast_api import auth
from tests.forecast.test_matrix_forecast import TODAY, book, setup_salary


@pytest.mark.asyncio
class TestBacktestInDerRegelantwort:
    async def test_kandidatentabelle_begruendet_die_regel(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            headers=headers,
        )

        assert resp.status_code == 200
        backtest = resp.json()["backtest"]
        assert backtest["ran"] is True
        assert backtest["holdout_months"] == 6
        assert backtest["holdout_from"] == "2026-03"
        assert backtest["holdout_to"] == "2026-08"

        keys = {candidate["key"] for candidate in backtest["candidates"]}
        assert "detected" in keys
        assert "none" in keys
        winners = [c for c in backtest["candidates"] if c["is_winner"]]
        assert len(winners) == 1
        assert winners[0]["key"] == "detected"

    async def test_gemessener_fehler_und_bandbreite_werden_ausgewiesen(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            headers=headers,
        )

        backtest = resp.json()["backtest"]
        # Das Gehalt ist exakt getroffen; die Bandbreite fällt auf die Untergrenze.
        assert Decimal(backtest["relative_error"]) == Decimal("0")
        assert Decimal(backtest["spread"]) == Decimal("0.05")
        assert backtest["beats_baseline"] is True
        assert backtest["replaced_detected"] is False

    async def test_ohne_historie_laeuft_kein_rueckvergleich(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        from app.services.models import ServiceType
        from tests.forecast.test_matrix_forecast import create_service_db

        user, mandant, account, run, partner, _ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        sparse = await create_service_db(
            db_session, partner.id, "Einmalig", ServiceType.supplier
        )
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=sparse.id,
            valuta_date="2026-07-10",
            amount="-500.00",
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/services/{sparse.id}/forecast-rule",
            headers=headers,
        )

        backtest = resp.json()["backtest"]
        assert backtest["ran"] is False
        assert backtest["candidates"] == []
        assert backtest["relative_error"] is None


@pytest.mark.asyncio
class TestUebersichtMitTreffsicherheit:
    async def test_zeile_und_summe_tragen_die_messung(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/services", headers=headers
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["backtested"] == 1
        assert body["replaced_by_backtest"] == 0
        assert body["weak_forecasts"] == 0
        assert Decimal(body["median_relative_error"]) == Decimal("0")

        row = next(r for r in body["services"] if r["service_name"] == "Gehalt")
        assert row["backtest_ran"] is True
        assert row["beats_baseline"] is True
        assert Decimal(row["relative_error"]) == Decimal("0")


@pytest.mark.asyncio
class TestPlanpostenStatus:
    """Ein Planposten verliert seine Wirkung, wird aber nicht geloescht. Die Liste muss
    zeigen, was davon noch zaehlt."""

    async def _items(self, client: AsyncClient, mandant, headers):
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items", headers=headers
        )
        return resp.json()

    async def _add(self, client, mandant, service, headers, period, amount):
        return await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
            json={"service_id": str(service.id), "period": period, "amount": amount},
            headers=headers,
        )

    async def test_kuenftiger_posten_ist_aktiv(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        created = await self._add(client, mandant, service, headers, "2027-04", "-1000.00")

        assert created.json()["status"] == "active"
        assert created.json()["remaining_in_month"] == "-1000.00"

    async def test_laufender_monat_wird_teilweise_verbraucht(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        # Stichtag ist der 15.09.2026; setup_salary bucht bis 08/2026.
        user, mandant, account, run, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await self._add(client, mandant, service, headers, "2026-09", "-5000.00")
        await book(
            db_session, account_id=account.id, import_run_id=run.id,
            service_id=service.id, valuta_date="2026-09-20", amount="-3000.00",
        )

        item = (await self._items(client, mandant, headers))[0]

        assert item["status"] == "partly_used"
        assert item["remaining_in_month"] == "-2000.00"

    async def test_erreichtes_ist_verbraucht_den_posten(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, account, run, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await self._add(client, mandant, service, headers, "2026-09", "-5000.00")
        await book(
            db_session, account_id=account.id, import_run_id=run.id,
            service_id=service.id, valuta_date="2026-09-20", amount="-5500.00",
        )

        item = (await self._items(client, mandant, headers))[0]

        assert item["status"] == "used"
        assert item["remaining_in_month"] == "0.00"

    async def test_vergangener_monat_ist_abgelaufen(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        created = await self._add(client, mandant, service, headers, "2026-07", "-800.00")

        assert created.json()["status"] == "expired"
        assert created.json()["remaining_in_month"] == "0.00"

    async def test_posten_desselben_monats_wirken_gemeinsam(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        """Zwei Posten im selben Monat teilen sich das Ist — sonst waere beide 'aktiv',
        obwohl zusammen nichts mehr aussteht."""
        user, mandant, account, run, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await self._add(client, mandant, service, headers, "2026-09", "-2000.00")
        await self._add(client, mandant, service, headers, "2026-09", "-1000.00")
        await book(
            db_session, account_id=account.id, import_run_id=run.id,
            service_id=service.id, valuta_date="2026-09-20", amount="-3000.00",
        )

        items = await self._items(client, mandant, headers)

        assert [i["status"] for i in items] == ["used", "used"]

    async def test_wirksames_steht_oben_abgelaufenes_unten(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        for period, amount in (
            ("2026-05", "-100.00"),
            ("2027-03", "-300.00"),
            ("2026-07", "-200.00"),
            ("2026-11", "-400.00"),
        ):
            await self._add(client, mandant, service, headers, period, amount)

        items = await self._items(client, mandant, headers)

        assert [i["period"] for i in items] == [
            "2026-11",  # wirksam, naechster zuerst
            "2027-03",
            "2026-07",  # abgelaufen, juengstes zuerst
            "2026-05",
        ]
        assert [i["status"] for i in items] == ["active", "active", "expired", "expired"]


@pytest.mark.asyncio
class TestHandgesetztesErkennen:
    """Wo von Hand eingegriffen wurde, muss die Liste es zeigen — sonst sieht eine
    Leistung mit +100 % Anpassung aus wie eine unberührte."""

    async def _rows(self, client: AsyncClient, mandant, headers):
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/services", headers=headers
        )
        return resp.json()

    async def test_unberuehrte_leistung_gilt_als_nicht_angepasst(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        body = await self._rows(client, mandant, headers)

        assert body["customised"] == 0
        row = next(r for r in body["services"] if r["service_name"] == "Gehalt")
        assert row["customised"] is False
        assert Decimal(row["adjustment_pct"]) == Decimal("0")
        assert row["shift_months"] == 0

    async def test_anpassung_im_automatikmodus_wird_sichtbar(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        """Der Fall, der in der Praxis untergegangen ist: Modus bleibt 'auto',
        aber der Betrag ist verdoppelt."""
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={"mode": "auto", "adjustment_pct": "100.00", "shift_months": 0},
            headers=headers,
        )

        body = await self._rows(client, mandant, headers)

        assert body["customised"] == 1
        row = next(r for r in body["services"] if r["service_name"] == "Gehalt")
        assert row["mode"] == "auto"  # der Modus verraet es eben nicht
        assert row["customised"] is True
        assert Decimal(row["adjustment_pct"]) == Decimal("100")

    async def test_zahlungsverzug_zaehlt_ebenfalls(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await client.put(
            f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule",
            json={"mode": "auto", "adjustment_pct": "0.00", "shift_months": 2},
            headers=headers,
        )

        row = next(
            r for r in (await self._rows(client, mandant, headers))["services"]
            if r["service_name"] == "Gehalt"
        )
        assert row["customised"] is True
        assert row["shift_months"] == 2

    async def test_planposten_zaehlt_ebenfalls(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
            json={
                "service_id": str(service.id),
                "period": "2027-04",
                "amount": "-1000.00",
            },
            headers=headers,
        )

        body = await self._rows(client, mandant, headers)
        assert body["customised"] == 1
        row = next(r for r in body["services"] if r["service_name"] == "Gehalt")
        assert row["customised"] is True

    async def test_zuruecksetzen_entfernt_die_markierung(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        url = f"/api/v1/mandants/{mandant.id}/services/{service.id}/forecast-rule"
        await client.put(
            url,
            json={"mode": "manual", "rule_type": "rolling_average", "params": {},
                  "adjustment_pct": "5.00", "shift_months": 1},
            headers=headers,
        )
        assert (await self._rows(client, mandant, headers))["customised"] == 1

        await client.delete(url, headers=headers)

        assert (await self._rows(client, mandant, headers))["customised"] == 0


@pytest.mark.asyncio
class TestUnsicherheitsband:
    async def test_band_umschliesst_den_erwartungswert_und_waechst(
        self, db_session: SQLModelSession
    ):
        _, mandant, *_ = await setup_salary(db_session)

        journal = JournalService(db_session, today=TODAY)
        liquidity = await journal.get_liquidity(mandant.id)

        first, last = liquidity.months[0], liquidity.months[-1]
        for month in (first, last):
            assert Decimal(month.closing_low) < Decimal(month.closing_balance)
            assert Decimal(month.closing_high) > Decimal(month.closing_balance)

        # Je weiter in die Zukunft, desto weniger sicher — das Band muss aufgehen.
        width_first = Decimal(first.closing_high) - Decimal(first.closing_low)
        width_last = Decimal(last.closing_high) - Decimal(last.closing_low)
        assert width_last > width_first

        lowest = Decimal(liquidity.lowest_balance)
        assert Decimal(liquidity.lowest_balance_low) <= lowest

    async def test_stresstest_traegt_kein_band(self, db_session: SQLModelSession):
        """Szenario und Band beantworten dieselbe Frage — zusammen wären sie doppelt."""
        _, mandant, *_ = await setup_salary(db_session)

        low = await JournalService(db_session, today=TODAY).get_liquidity(
            mandant.id, scenario=Scenario.low
        )

        for month in low.months:
            assert month.closing_low == month.closing_balance
            assert month.closing_high == month.closing_balance

    async def test_planposten_tragen_keine_unsicherheit(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        """Ein bekannter Betrag wird nicht geschätzt und weitet das Band nicht auf."""
        user, mandant, _, _, _, service = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        before = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)
        width_before = Decimal(before.months[-1].closing_high) - Decimal(
            before.months[-1].closing_low
        )

        # Die Prognose für 10/2026 durch einen bekannten Betrag ersetzen.
        await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/planned-items",
            json={
                "service_id": str(service.id),
                "period": "2026-10",
                "amount": "-3000.00",
            },
            headers=headers,
        )

        after = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)
        width_after = Decimal(after.months[-1].closing_high) - Decimal(
            after.months[-1].closing_low
        )

        assert width_after < width_before


@pytest.mark.asyncio
class TestSnapshots:
    async def _snapshot(self, db_session: SQLModelSession, mandant_id, today=TODAY):
        """Legt einen Snapshot mit fest eingestelltem Stichtag an."""
        journal = JournalService(db_session, today=today)
        forecast = ForecastService(db_session, today=today)
        liquidity = await journal.get_liquidity(mandant_id)
        return await forecast.create_snapshot(
            mandant_id, CreateSnapshotRequest(label="Planstand"), liquidity
        )

    async def test_friert_die_kurve_ein(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        snapshot = await self._snapshot(db_session, mandant.id)

        assert snapshot.label == "Planstand"
        assert snapshot.as_of == "2026-09-15"
        assert snapshot.scenario == "expected"
        # 09/2026 bis 12/2027 — der Horizont endet im Dezember des Folgejahres.
        assert snapshot.month_count == 16
        assert snapshot.months[0].period == "2026-09"
        assert snapshot.months[-1].period == "2027-12"

    async def test_ohne_abgelaufenen_monat_gibt_es_nichts_zu_messen(
        self, db_session: SQLModelSession
    ):
        _, mandant, *_ = await setup_salary(db_session)

        snapshot = await self._snapshot(db_session, mandant.id)

        assert snapshot.elapsed_months == 0
        assert snapshot.mean_absolute_deviation is None
        assert snapshot.latest_deviation is None
        assert all(month.actual_net is None for month in snapshot.months[1:])

    async def test_vergleicht_plan_gegen_tatsaechliche_buchungen(
        self, db_session: SQLModelSession
    ):
        _, mandant, account, run, _, service = await setup_salary(db_session)
        snapshot = await self._snapshot(db_session, mandant.id)

        # Oktober läuft ab: Statt der prognostizierten -3.000 kommen -3.500.
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2026-10-28",
            amount="-3500.00",
        )

        later = ForecastService(db_session, today=date(2026, 11, 5))
        detail = await later.get_snapshot(mandant.id, snapshot.id)

        october = next(month for month in detail.months if month.period == "2026-10")
        assert october.is_complete is True
        assert october.planned_net == "-3000.00"
        assert october.actual_net == "-3500.00"
        # Im Oktober selbst 500 schlechter als geplant.
        assert Decimal(october.net_deviation) == Decimal("-500.00")
        # Aufgelaufen steht der Saldo trotzdem besser da: Im September war das erwartete
        # Gehalt gar nicht geflossen, das sind +3.000 gegenüber dem Plan.
        september = next(month for month in detail.months if month.period == "2026-09")
        assert Decimal(september.deviation) == Decimal("3000.00")
        assert Decimal(october.deviation) == Decimal("2500.00")
        assert detail.elapsed_months == 2  # 09/2026 und 10/2026
        assert detail.latest_deviation == "2500.00"

    async def test_laufender_monat_zaehlt_nicht_in_die_messung(
        self, db_session: SQLModelSession
    ):
        """Der angebrochene Monat wird angezeigt, verfälscht die Kennzahl aber nicht."""
        _, mandant, *_ = await setup_salary(db_session)
        snapshot = await self._snapshot(db_session, mandant.id)

        later = ForecastService(db_session, today=date(2026, 10, 10))
        detail = await later.get_snapshot(mandant.id, snapshot.id)

        october = next(month for month in detail.months if month.period == "2026-10")
        assert october.is_complete is False
        assert october.actual_net is not None  # sichtbar
        assert detail.elapsed_months == 1  # aber nur der September zählt

    async def test_startsaldo_enthaelt_den_stichtag_bereits(
        self, db_session: SQLModelSession
    ):
        """Nur was nach dem Stichtag gebucht wurde, gilt als noch offenes Ist."""
        _, mandant, account, run, _, service = await setup_salary(db_session)
        snapshot = await self._snapshot(db_session, mandant.id)

        # Eine Buchung vom 10.09. liegt vor dem Stichtag 15.09. und steckt schon
        # im Startsaldo — sie darf im September-Ist nicht noch einmal auftauchen.
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2026-09-10",
            amount="-777.00",
        )
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2026-09-20",
            amount="-100.00",
        )

        later = ForecastService(db_session, today=date(2026, 10, 1))
        detail = await later.get_snapshot(mandant.id, snapshot.id)

        september = next(month for month in detail.months if month.period == "2026-09")
        assert september.actual_net == "-100.00"

    async def test_liste_und_loeschen_ueber_http(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        created = await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/snapshots",
            json={"label": "Vor der Budgetrunde", "scenario": "low"},
            headers=headers,
        )
        assert created.status_code == 201
        snapshot_id = created.json()["id"]
        assert created.json()["scenario"] == "low"

        listed = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/snapshots", headers=headers
        )
        assert [row["id"] for row in listed.json()] == [snapshot_id]
        # Die Liste bleibt schlank — die Monatstabelle steckt nur im Detail.
        assert listed.json()[0].get("months", []) == []

        deleted = await client.delete(
            f"/api/v1/mandants/{mandant.id}/forecast/snapshots/{snapshot_id}",
            headers=headers,
        )
        assert deleted.status_code == 204

        after = await client.get(
            f"/api/v1/mandants/{mandant.id}/forecast/snapshots", headers=headers
        )
        assert after.json() == []

    async def test_unbekanntes_szenario_wird_abgelehnt(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/snapshots",
            json={"scenario": "traumhaft"},
            headers=headers,
        )

        assert resp.status_code == 422

    async def test_fremder_snapshot_ist_nicht_erreichbar(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        headers = await auth(client, user, mandant)
        created = await client.post(
            f"/api/v1/mandants/{mandant.id}/forecast/snapshots",
            json={},
            headers=headers,
        )
        snapshot_id = created.json()["id"]

        from uuid import uuid4

        resp = await client.get(
            f"/api/v1/mandants/{uuid4()}/forecast/snapshots/{snapshot_id}",
            headers=headers,
        )

        assert resp.status_code in (403, 404)
