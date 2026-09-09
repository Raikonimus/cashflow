"""Prognosewerte in der Einnahmen-/Ausgaben-Matrix und in der Liquiditätsvorschau."""
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelSession

from app.auth.models import UserRole
from app.imports.models import JournalLine, JournalLineSplit
from app.journal.service import JournalService
from app.services.models import Service, ServiceType
from tests.journal import (
    assign_user_to_mandant,
    create_account_db,
    create_import_run_db,
    create_mandant,
    create_partner_db,
    create_user,
    get_auth_token,
    utcnow,
)

TODAY = date(2026, 9, 15)


async def create_service_db(
    session: AsyncSession,
    partner_id: UUID,
    name: str,
    service_type: ServiceType = ServiceType.supplier,
) -> Service:
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type=service_type.value,
        tax_rate=Decimal("0.00"),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


async def book(
    session: AsyncSession,
    *,
    account_id: UUID,
    import_run_id: UUID,
    service_id: UUID,
    valuta_date: str,
    amount: str,
) -> None:
    line = JournalLine(
        account_id=account_id,
        import_run_id=import_run_id,
        valuta_date=valuta_date,
        booking_date=valuta_date,
        amount=Decimal(amount),
        currency="EUR",
        text="Buchung",
        created_at=utcnow(),
    )
    session.add(line)
    await session.commit()
    await session.refresh(line)
    session.add(
        JournalLineSplit(
            journal_line_id=line.id,
            service_id=service_id,
            amount=Decimal(amount),
            assignment_mode="auto",
            amount_consistency_ok=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    await session.commit()


async def setup_salary(db_session: SQLModelSession, *, through_month: int = 8):
    """Monatliches Gehalt von 01/2025 bis 08/2026, im Juni doppelt."""
    user = await create_user(db_session, "acc@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id, opening_balance=Decimal("10000.00"))
    run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
    partner = await create_partner_db(db_session, mandant.id, "Mitarbeiter")
    service = await create_service_db(db_session, partner.id, "Gehalt", ServiceType.employee)

    for year in (2024, 2025, 2026):
        for month in range(1, 13):
            if year == 2026 and month > through_month:
                continue
            amount = "-6000.00" if month == 6 else "-3000.00"
            await book(
                db_session,
                account_id=account.id,
                import_run_id=run.id,
                service_id=service.id,
                valuta_date=f"{year}-{month:02d}-28",
                amount=amount,
            )
    return user, mandant, account, run, partner, service


def cells_of(payload: dict, service_name: str) -> dict:
    for section in payload["sections"].values():
        for group in section["groups"]:
            for service in group["services"]:
                if service["service_name"] == service_name:
                    return service
    raise AssertionError(f"Leistung {service_name} nicht in der Matrix")


@pytest.mark.asyncio
class TestMatrixForecast:
    async def test_folgejahr_ist_vollstaendig_prognose(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2027
        )

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["forecast_rule"] == "fixed_recurring"
        assert row["forecast_confidence"] == "high"
        assert row["cells"]["jan"]["gross"] == "-3000.00"
        assert row["cells"]["jun"]["gross"] == "-6000.00"  # Sondermonat erkannt
        assert row["cells"]["jan"]["is_forecast"] is True
        assert row["cells"]["year_total"]["gross"] == "-39000.00"
        assert matrix.first_forecast_month == 1

    async def test_laufendes_jahr_trennt_ist_von_prognose(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2026
        )

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert matrix.first_forecast_month == 9
        # Januar bis August sind gebucht.
        assert row["cells"]["jan"]["is_forecast"] is False
        assert row["cells"]["aug"]["gross"] == "-3000.00"
        assert row["cells"]["aug"]["is_forecast"] is False
        # Oktober bis Dezember sind Prognose.
        assert row["cells"]["oct"]["gross"] == "-3000.00"
        assert row["cells"]["oct"]["is_forecast"] is True
        # Die Jahressumme mischt beides und ist als Prognose markiert.
        assert row["cells"]["year_total"]["is_forecast"] is True

    async def test_laufender_monat_ergaenzt_nur_den_fehlbetrag(self, db_session: SQLModelSession):
        _, mandant, account, run, _, service = await setup_salary(db_session)
        # Im September sind erst 1.000 € von erwarteten 3.000 € gebucht.
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2026-09-05",
            amount="-1000.00",
        )

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2026
        )

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["sep"]["gross"] == "-3000.00"
        assert row["cells"]["sep"]["is_forecast"] is True

    async def test_bereits_uebererfuellter_monat_wird_nicht_aufgestockt(
        self, db_session: SQLModelSession
    ):
        _, mandant, account, run, _, service = await setup_salary(db_session)
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2026-09-05",
            amount="-5000.00",
        )

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2026
        )

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert row["cells"]["sep"]["gross"] == "-5000.00"
        assert row["cells"]["sep"]["is_forecast"] is False

    async def test_vergangenes_jahr_bleibt_unveraendert(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2025
        )

        row = cells_of(matrix.model_dump(), "Gehalt")
        assert matrix.first_forecast_month is None
        assert row["forecast_rule"] is None
        assert all(
            row["cells"][key]["is_forecast"] is False
            for key in ("year_total", "jan", "jun", "dec")
        )

    async def test_leistung_ohne_ausreichende_historie_bleibt_sichtbar(
        self, db_session: SQLModelSession
    ):
        user, mandant, account, run, partner, _ = await setup_salary(db_session)
        sporadic = await create_service_db(db_session, partner.id, "Projekt X", ServiceType.customer)
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=sporadic.id,
            valuta_date="2026-07-10",
            amount="20000.00",
        )

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2027
        )

        row = cells_of(matrix.model_dump(), "Projekt X")
        assert row["forecast_rule"] == "none"
        assert row["forecast_confidence"] is None
        assert row["forecast_reason"]
        assert row["cells"]["jan"]["gross"] == "0.00"
        # Grau bleibt die Zelle trotzdem — sie liegt im Prognosezeitraum.
        assert row["cells"]["jan"]["is_forecast"] is True

    async def test_gruppensumme_erbt_die_prognosemarkierung(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        matrix = await JournalService(db_session, today=TODAY).get_income_expense_matrix(
            mandant_id=mandant.id, year=2027
        )

        expense = matrix.model_dump()["sections"]["expense"]
        assert expense["totals"]["jan"]["is_forecast"] is True
        group = next(g for g in expense["groups"] if g["services"])
        assert group["subtotal_cells"]["jan"]["is_forecast"] is True


@pytest.mark.asyncio
class TestLiquidity:
    async def test_kurve_startet_beim_aktuellen_kontostand(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        result = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)

        # Startsaldo 10.000 abzüglich aller gebuchten Gehälter.
        assert result.start_balance == result.months[0].opening_balance
        assert result.months[0].period == "2026-09"
        assert result.months[-1].period == "2027-12"

    async def test_monate_bauen_aufeinander_auf(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        result = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)

        for earlier, later in zip(result.months, result.months[1:]):
            assert earlier.closing_balance == later.opening_balance
        first = result.months[0]
        assert Decimal(first.closing_balance) == Decimal(first.opening_balance) + Decimal(first.net)

    async def test_weist_tiefpunkt_aus(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_salary(db_session)

        result = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)

        # Reine Ausgabenleistung — der Tiefpunkt liegt im letzten Monat.
        assert result.lowest_period == result.months[-1].period
        assert Decimal(result.lowest_balance) == Decimal(result.months[-1].closing_balance)

    async def test_meldet_nicht_zugeordnete_buchungen(self, db_session: SQLModelSession):
        user, mandant, account, run, *_ = await setup_salary(db_session)
        # Buchung ohne Split — nicht prognostizierbar.
        line = JournalLine(
            account_id=account.id,
            import_run_id=run.id,
            valuta_date="2026-03-10",
            booking_date="2026-03-10",
            amount=Decimal("-1200.00"),
            currency="EUR",
            created_at=utcnow(),
        )
        db_session.add(line)
        await db_session.commit()

        result = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)

        assert Decimal(result.uncovered_average_per_month) == Decimal("-100.00")


    async def test_leistungen_ohne_regel_zaehlen_als_nicht_abgedeckt(
        self, db_session: SQLModelSession
    ):
        _, mandant, account, run, partner, _ = await setup_salary(db_session)
        # Einmalige Projekteinnahme: in der Matrix sichtbar, aber nicht prognostizierbar.
        sporadic = await create_service_db(db_session, partner.id, "Projekt X", ServiceType.customer)
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=sporadic.id,
            valuta_date="2026-07-10",
            amount="12000.00",
        )

        result = await JournalService(db_session, today=TODAY).get_liquidity(mandant.id)

        assert Decimal(result.uncovered_average_per_month) == Decimal("1000.00")


@pytest.mark.asyncio
class TestEndpoints:
    async def test_liquiditaet_ueber_http(self, client: AsyncClient, db_session: SQLModelSession):
        user, mandant, *_ = await setup_salary(db_session)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/reports/liquidity",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["currency"] == "EUR"
        assert len(body["months"]) > 0

    async def test_jahresliste_nennt_prognosejahre(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_salary(db_session)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/journal/years",
            headers={"Authorization": f"Bearer {token}"},
        )

        body = resp.json()
        assert body["forecast_years"] == [date.today().year, date.today().year + 1]

    async def test_liquiditaet_erfordert_authentifizierung(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        mandant = await create_mandant(db_session)

        resp = await client.get(f"/api/v1/mandants/{mandant.id}/reports/liquidity")

        assert resp.status_code == 401
