"""Kontostand zu jedem Monatsende — Ist, soweit gebucht, sonst Prognose."""

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
    session: AsyncSession, partner_id: UUID, name: str
) -> Service:
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type=ServiceType.supplier.value,
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
    service_id: UUID | None,
    valuta_date: str,
    amount: str,
    currency: str = "EUR",
) -> None:
    line = JournalLine(
        account_id=account_id,
        import_run_id=import_run_id,
        valuta_date=valuta_date,
        booking_date=valuta_date,
        amount=Decimal(amount),
        currency=currency,
        text="Buchung",
        created_at=utcnow(),
    )
    session.add(line)
    await session.commit()
    await session.refresh(line)
    if service_id is not None:
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


async def setup_miete(db_session: SQLModelSession, *, through_month: int = 8):
    """Monatliche Miete von 01/2025 bis 08/2026, Startsaldo 10.000 €."""
    user = await create_user(db_session, "acc@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(
        db_session, mandant.id, opening_balance=Decimal("10000.00")
    )
    run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
    partner = await create_partner_db(db_session, mandant.id, "Vermieter")
    service = await create_service_db(db_session, partner.id, "Miete")

    for year in (2025, 2026):
        for month in range(1, 13):
            if year == 2026 and month > through_month:
                continue
            await book(
                db_session,
                account_id=account.id,
                import_run_id=run.id,
                service_id=service.id,
                valuta_date=f"{year}-{month:02d}-05",
                amount="-1000.00",
            )
    return user, mandant, account, run, service


def month(payload: dict, number: int) -> dict:
    return payload["months"][number - 1]


@pytest.mark.asyncio
class TestSaldoZeitleiste:
    async def test_vergangenes_jahr_ist_reines_ist(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_miete(db_session)

        timeline = (
            await JournalService(db_session, today=TODAY).get_balance_timeline(
                mandant_id=mandant.id, year=2025
            )
        ).model_dump()

        # 2025 ist das erste Buchungsjahr: Start ist der Anfangsbestand selbst.
        assert timeline["opening_balance"] == "10000.00"
        assert timeline["first_forecast_month"] is None
        assert month(timeline, 1)["closing_balance"] == "9000.00"
        assert month(timeline, 6)["closing_balance"] == "4000.00"
        assert month(timeline, 12)["closing_balance"] == "-2000.00"
        assert all(not entry["is_forecast"] for entry in timeline["months"])

    async def test_uebertrag_aus_vorjahren_steht_im_januar(
        self, db_session: SQLModelSession
    ):
        _, mandant, *_ = await setup_miete(db_session)

        timeline = (
            await JournalService(db_session, today=TODAY).get_balance_timeline(
                mandant_id=mandant.id, year=2026
            )
        ).model_dump()

        # Der Startwert des Folgejahres ist der Endwert des Vorjahres.
        assert timeline["opening_balance"] == "-2000.00"
        assert month(timeline, 1)["closing_balance"] == "-3000.00"

    async def test_laufendes_jahr_trennt_ist_von_prognose(
        self, db_session: SQLModelSession
    ):
        _, mandant, *_ = await setup_miete(db_session)

        timeline = (
            await JournalService(db_session, today=TODAY).get_balance_timeline(
                mandant_id=mandant.id, year=2026
            )
        ).model_dump()

        assert timeline["first_forecast_month"] == 9
        assert month(timeline, 8)["is_forecast"] is False
        assert month(timeline, 8)["closing_balance"] == "-10000.00"
        assert month(timeline, 9)["is_forecast"] is True
        # Die Prognose setzt die Miete fort: je Monat 1.000 € weniger.
        assert month(timeline, 9)["closing_balance"] == "-11000.00"
        assert month(timeline, 12)["closing_balance"] == "-14000.00"

    async def test_grenze_ist_dieselbe_wie_in_der_matrix(
        self, db_session: SQLModelSession
    ):
        """Leiste und Matrix stehen untereinander — sie müssen dieselbe Grenze ziehen."""
        _, mandant, *_ = await setup_miete(db_session)
        svc = JournalService(db_session, today=TODAY)

        for year in (2025, 2026, 2027):
            timeline = await svc.get_balance_timeline(mandant_id=mandant.id, year=year)
            matrix = await svc.get_income_expense_matrix(
                mandant_id=mandant.id, year=year
            )
            assert timeline.first_forecast_month == matrix.first_forecast_month, year

    async def test_prognosemonate_stimmen_mit_der_liquiditaetskurve_ueberein(
        self, db_session: SQLModelSession
    ):
        """Der Zwillings-Test: dieselbe Zahl darf nicht zweimal verschieden entstehen.

        Die Leiste hier und die Kurve im Dashboard beantworten für die Prognosemonate
        dieselbe Frage. Weichen sie ab, ist eine von beiden falsch — und keiner sieht es,
        weil beide Seiten für sich plausibel aussehen.
        """
        _, mandant, *_ = await setup_miete(db_session)
        svc = JournalService(db_session, today=TODAY)

        liquidity = await svc.get_liquidity(mandant.id)
        by_period = {entry.period: entry.closing_balance for entry in liquidity.months}
        assert by_period, "Ohne Prognosemonate prüft der Test nichts"

        checked = 0
        for year in (2026, 2027):
            timeline = await svc.get_balance_timeline(mandant_id=mandant.id, year=year)
            for entry in timeline.months:
                period = f"{year:04d}-{entry.month:02d}"
                if period not in by_period:
                    continue
                assert entry.is_forecast is True, period
                assert entry.closing_balance == by_period[period], period
                checked += 1
        assert checked == len(by_period)

    async def test_jenseits_des_horizonts_zeigt_nur_gebuchtes(
        self, db_session: SQLModelSession
    ):
        _, mandant, account, run, service = await setup_miete(db_session)
        # Eine einzelne Buchung jenseits des Horizonts macht das Jahr erreichbar.
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2029-03-10",
            amount="-500.00",
        )

        timeline = (
            await JournalService(db_session, today=TODAY).get_balance_timeline(
                mandant_id=mandant.id, year=2029
            )
        ).model_dump()

        assert timeline["first_forecast_month"] is None
        # Gebucht ist gebucht — der März zeigt die Buchung, nicht eine Prognose.
        assert month(timeline, 3)["is_forecast"] is False
        assert Decimal(month(timeline, 3)["closing_balance"]) - Decimal(
            month(timeline, 2)["closing_balance"]
        ) == Decimal("-500.00")
        # Ohne Buchung bewegt sich nichts — und es wird auch nichts erfunden.
        assert (
            month(timeline, 2)["closing_balance"]
            == month(timeline, 1)["closing_balance"]
        )

    async def test_letzter_ist_monat_entspricht_dem_kontostand(
        self, db_session: SQLModelSession
    ):
        """Welche Konten und Währungen zählen, darf die Leiste nicht anders sehen.

        get_account_balances() entscheidet das für das Dashboard, die Leiste stellt
        dieselbe Bedingung noch einmal in SQL. Nach der letzten Buchung — hier August
        2026 — müssen beide auf denselben Betrag kommen.
        """
        _, mandant, account, run, service = await setup_miete(db_session)
        # Eine Fremdwährungsbuchung und ein zweites Konto: beides muss auf beiden Wegen
        # gleich behandelt werden.
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2026-04-10",
            amount="-4444.00",
            currency="CHF",
        )
        zweiter_nutzer = await create_user(
            db_session, "zweit@test.com", UserRole.accountant
        )
        zweites = await create_account_db(
            db_session,
            mandant.id,
            name="Zweitkonto",
            opening_balance=Decimal("2500.00"),
        )
        zweiter_run = await create_import_run_db(
            db_session, zweites.id, mandant.id, zweiter_nutzer.id
        )
        await book(
            db_session,
            account_id=zweites.id,
            import_run_id=zweiter_run.id,
            service_id=service.id,
            valuta_date="2026-02-20",
            amount="300.00",
        )

        svc = JournalService(db_session, today=TODAY)
        timeline = await svc.get_balance_timeline(mandant_id=mandant.id, year=2026)
        balances = await svc.get_account_balances(mandant.id)

        gesamt = next(
            entry for entry in balances.totals if entry.currency == "EUR"
        ).current_balance
        august = month(timeline.model_dump(), 8)
        assert august["is_forecast"] is False
        assert august["closing_balance"] == gesamt

    async def test_fremdwaehrung_zaehlt_nicht_mit(self, db_session: SQLModelSession):
        _, mandant, account, run, service = await setup_miete(db_session)
        await book(
            db_session,
            account_id=account.id,
            import_run_id=run.id,
            service_id=service.id,
            valuta_date="2025-03-10",
            amount="-9999.00",
            currency="CHF",
        )

        timeline = (
            await JournalService(db_session, today=TODAY).get_balance_timeline(
                mandant_id=mandant.id, year=2025
            )
        ).model_dump()

        assert month(timeline, 3)["closing_balance"] == "7000.00"

    async def test_fremder_mandant_faerbt_nicht_ab(self, db_session: SQLModelSession):
        _, mandant, *_ = await setup_miete(db_session)

        fremd_user = await create_user(
            db_session, "fremd@test.com", UserRole.accountant
        )
        fremd_mandant = await create_mandant(db_session, "Fremd GmbH")
        await assign_user_to_mandant(db_session, fremd_user, fremd_mandant)
        fremd_account = await create_account_db(
            db_session,
            fremd_mandant.id,
            name="Fremdkonto",
            opening_balance=Decimal("500000.00"),
        )
        fremd_run = await create_import_run_db(
            db_session, fremd_account.id, fremd_mandant.id, fremd_user.id
        )
        await book(
            db_session,
            account_id=fremd_account.id,
            import_run_id=fremd_run.id,
            service_id=None,
            valuta_date="2025-03-10",
            amount="-77777.00",
        )

        timeline = (
            await JournalService(db_session, today=TODAY).get_balance_timeline(
                mandant_id=mandant.id, year=2025
            )
        ).model_dump()

        assert timeline["opening_balance"] == "10000.00"
        assert month(timeline, 3)["closing_balance"] == "7000.00"

    async def test_endpunkt_liefert_die_zeitleiste(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_miete(db_session)
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/reports/balance-timeline",
            params={"year": 2025},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["year"] == 2025
        assert payload["currency"] == "EUR"
        assert len(payload["months"]) == 12
        assert month(payload, 12)["closing_balance"] == "-2000.00"

    async def test_endpunkt_verweigert_fremden_mandanten(
        self, client: AsyncClient, db_session: SQLModelSession
    ):
        user, mandant, *_ = await setup_miete(db_session)
        fremd_mandant = await create_mandant(db_session, "Fremd GmbH")
        token = await get_auth_token(client, user, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{fremd_mandant.id}/reports/balance-timeline",
            params={"year": 2025},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403
