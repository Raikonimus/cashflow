import math
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.forecast.backtest import combined_uncertainty
from app.forecast.profiler import index_to_year_month, month_index
from app.forecast.rules import Scenario
from app.forecast.service import (
    ForecastContext,
    ForecastService,
    horizon_end_index,
)
from app.imports.models import JournalLine, JournalLineSplit
from app.journal.schemas import (
    AccountBalanceRow,
    AccountBalancesResponse,
    AccountBalanceTotal,
    BulkAssignResponse,
    IncomeExpenseGroupRow,
    IncomeExpenseMatrixResponse,
    IncomeExpenseSection,
    IncomeExpenseServiceRow,
    JournalLineResponse,
    JournalYearsResponse,
    LiquidityMonth,
    LiquidityResponse,
    MatrixCell,
    MatrixCells,
    PaginatedJournalResponse,
)
from app.partners.models import AuditLog, Partner
from app.services.models import (
    Service,
    ServiceGroup,
    ServiceGroupAssignment,
    ServiceGroupSection,
    section_for_service,
)
from app.services.service import ServiceManagementService
from app.tenants.models import Account

log = structlog.get_logger()

INTERNAL_UNMAPPED_DATA_KEYS = {"_cashflow_source_values"}
MONTH_KEYS = [
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
]

_ZERO = Decimal("0.00")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sanitize_unmapped_data(unmapped_data: Any) -> Any:
    if not isinstance(unmapped_data, dict):
        return unmapped_data

    sanitized = {
        key: value
        for key, value in unmapped_data.items()
        if key not in INTERNAL_UNMAPPED_DATA_KEYS
    }
    return sanitized or None


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _as_money(value: Decimal) -> str:
    return str(_round_money(value))


def _empty_cells() -> dict[str, dict[str, Decimal]]:
    cells: dict[str, dict[str, Decimal]] = {
        "year_total": {"gross": Decimal("0"), "net": Decimal("0")},
    }
    for month_key in MONTH_KEYS:
        cells[month_key] = {"gross": Decimal("0"), "net": Decimal("0")}
    return cells


def _forecast_years(today: date) -> list[int]:
    """Jahre, die über den Prognosehorizont erreichbar sind (laufendes und Folgejahr)."""
    return list(range(today.year, index_to_year_month(horizon_end_index(today))[0] + 1))


def _empty_flags() -> dict[str, bool]:
    return {key: False for key in ["year_total", *MONTH_KEYS]}


def _to_cells_payload(
    cells: dict[str, dict[str, Decimal]],
    flags: dict[str, bool] | None = None,
) -> MatrixCells:
    marks = flags or _empty_flags()

    def cell(key: str) -> MatrixCell:
        return MatrixCell(
            gross=_as_money(cells[key]["gross"]),
            net=_as_money(cells[key]["net"]),
            is_forecast=marks[key],
        )

    return MatrixCells(
        year_total=cell("year_total"),
        jan=cell("jan"),
        feb=cell("feb"),
        mar=cell("mar"),
        apr=cell("apr"),
        may=cell("may"),
        jun=cell("jun"),
        jul=cell("jul"),
        aug=cell("aug"),
        sep=cell("sep"),
        oct=cell("oct"),
        nov=cell("nov"),
        dec=cell("dec"),
    )


def _month_key_from_valuta_date(valuta_date: str) -> str | None:
    try:
        month = int(valuta_date[5:7])
    except (TypeError, ValueError):
        return None
    if month < 1 or month > 12:
        return None
    return MONTH_KEYS[month - 1]


# Sortierung: partner_name / service_name brauchen JOINs, diese hier sind
# einfache SQL-Spalten.
_SQL_SORT_COLS = {"valuta_date", "booking_date", "amount", "text"}


class JournalService:
    def __init__(self, session: AsyncSession, *, today: date | None = None) -> None:
        self._session = session
        # Injizierbar, damit Prognosetests nicht von der Systemuhr abhängen.
        self._today = today or date.today()

    # ─── List lines ──────────────────────────────────────────────────────────

    async def list_lines(
        self,
        mandant_id: UUID,
        *,
        account_id: UUID | None = None,
        partner_id: UUID | None = None,
        service_id: UUID | None = None,
        year: int | None = None,
        month: int | None = None,
        has_partner: bool | None = None,
        search: str = "",
        sort_by: str = "valuta_date",
        sort_dir: str = "desc",
        page: int = 1,
        size: int = 50,
    ) -> PaginatedJournalResponse:
        size = min(size, 200)
        offset = (page - 1) * size

        # All account IDs belonging to this mandant (security boundary)
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        if account_id is not None:
            if account_id not in mandant_account_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account does not belong to this mandant",
                )
            account_ids_filter = {account_id}
        else:
            account_ids_filter = mandant_account_ids

        query = select(JournalLine).where(
            col(JournalLine.account_id).in_(account_ids_filter)
        )

        if partner_id is not None:
            query = query.where(JournalLine.partner_id == partner_id)

        if service_id is not None:
            query = query.join(
                JournalLineSplit,
                JournalLineSplit.journal_line_id == JournalLine.id,  # type: ignore[arg-type]
            ).where(JournalLineSplit.service_id == service_id)

        if has_partner is True:
            query = query.where(JournalLine.partner_id.is_not(None))
        elif has_partner is False:
            query = query.where(JournalLine.partner_id.is_(None))

        if year is not None and month is not None:
            prefix = f"{year:04d}-{month:02d}-"
            query = query.where(
                text("journal_lines.valuta_date LIKE :valuta_prefix").bindparams(
                    valuta_prefix=f"{prefix}%"
                )
            )
        elif year is not None:
            query = query.where(
                text("journal_lines.valuta_date LIKE :valuta_year").bindparams(
                    valuta_year=f"{year:04d}-%"
                )
            )

        if search:
            # Always JOIN partners for search (avoid duplicate join if also sorting by partner_name)
            term = f"%{search.lower()}%"
            query = query.outerjoin(
                Partner, Partner.id == JournalLine.partner_id
            ).where(  # type: ignore[arg-type]
                or_(
                    func.lower(func.coalesce(JournalLine.text, "")).like(term),
                    func.lower(func.coalesce(JournalLine.partner_name_raw, "")).like(
                        term
                    ),
                    func.lower(
                        func.coalesce(Partner.display_name, Partner.name, "")
                    ).like(term),
                )
            )

        order_dir = "DESC" if sort_dir == "desc" else "ASC"
        if sort_by in _SQL_SORT_COLS:
            order_expr = text(f"{sort_by} {order_dir}")
        elif sort_by == "partner_name":
            # JOIN partners so we can ORDER BY coalesce(display_name, name) globally
            # Only join if not already joined via search
            if not search:  # search already added the join
                query = query.outerjoin(Partner, Partner.id == JournalLine.partner_id)  # type: ignore[arg-type]
            order_expr = text(
                f"lower(coalesce(partners.display_name, partners.name, journal_lines.partner_name_raw, '')) {order_dir}"
            )
        elif sort_by == "service_name":
            query = query.outerjoin(
                JournalLineSplit,
                JournalLineSplit.journal_line_id == JournalLine.id,  # type: ignore[arg-type]
            ).outerjoin(
                Service, Service.id == JournalLineSplit.service_id
            )  # type: ignore[arg-type]
            order_expr = text(f"lower(coalesce(services.name, '')) {order_dir}")
        else:
            order_expr = text("valuta_date DESC")  # fallback

        count_res = await self._session.exec(query)
        total = len(count_res.all())

        data_res = await self._session.exec(
            query.order_by(order_expr).offset(offset).limit(size)
        )
        lines = data_res.all()

        # Batch-load partner names (prefer display_name)
        partner_ids = {ln.partner_id for ln in lines if ln.partner_id}
        partner_names: dict = {}
        if partner_ids:
            p_res = await self._session.exec(select(Partner))
            partner_names = {
                partner.id: partner.display_name or partner.name
                for partner in p_res.all()
                if partner.id in partner_ids
            }

        service_ids = {sp.service_id for ln in lines for sp in []}
        # Batch-load splits for the returned lines
        line_ids_batch = [ln.id for ln in lines]
        splits_by_line: dict[UUID, list[JournalLineSplit]] = {}
        if line_ids_batch:
            all_splits = (
                await self._session.exec(
                    select(JournalLineSplit).where(
                        JournalLineSplit.journal_line_id.in_(line_ids_batch)  # type: ignore[attr-defined]
                    )
                )
            ).all()
            for sp in all_splits:
                splits_by_line.setdefault(sp.journal_line_id, []).append(sp)

        service_ids = {sp.service_id for sps in splits_by_line.values() for sp in sps}
        service_names: dict = {}
        if service_ids:
            s_res = await self._session.exec(
                select(Service.id, Service.name).where(col(Service.id).in_(service_ids))
            )
            service_names = {
                service_id: service_name for service_id, service_name in s_res.all()
            }

        items = [
            JournalLineResponse(
                **{
                    **{
                        k: v for k, v in ln.model_dump().items() if k != "unmapped_data"
                    },
                    "unmapped_data": _sanitize_unmapped_data(ln.unmapped_data),
                },
                splits=[
                    {
                        "service_id": sp.service_id,
                        "service_name": service_names.get(sp.service_id),
                        "amount": sp.amount,
                        "assignment_mode": sp.assignment_mode,
                        "amount_consistency_ok": sp.amount_consistency_ok,
                    }
                    for sp in splits_by_line.get(ln.id, [])
                ],
                partner_name=(
                    partner_names.get(ln.partner_id) if ln.partner_id else None
                ),
            )
            for ln in lines
        ]

        return PaginatedJournalResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=math.ceil(total / size) if total > 0 else 1,
        )

    async def list_years(
        self,
        mandant_id: UUID,
        *,
        account_id: UUID | None = None,
    ) -> JournalYearsResponse:
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        if account_id is not None:
            if account_id not in mandant_account_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account does not belong to this mandant",
                )
            account_ids_filter = {account_id}
        else:
            account_ids_filter = mandant_account_ids

        if not account_ids_filter:
            return JournalYearsResponse(
                years=[], forecast_years=_forecast_years(self._today)
            )

        years_query = (
            select(func.substr(JournalLine.valuta_date, 1, 4).label("year"))
            .where(col(JournalLine.account_id).in_(account_ids_filter))
            .group_by(text("year"))
            .order_by(text("year DESC"))
        )
        rows = (await self._session.exec(years_query)).all()

        years: list[int] = []
        for row in rows:
            try:
                years.append(int(str(row)))
            except (TypeError, ValueError):
                continue
        return JournalYearsResponse(
            years=years, forecast_years=_forecast_years(self._today)
        )

    # ─── Kontosalden ─────────────────────────────────────────────────────────

    async def get_account_balances(self, mandant_id: UUID) -> AccountBalancesResponse:
        """Aktueller Kontostand je Konto: Startsaldo + Summe der importierten Buchungen.

        Gerechnet wird nur mit Buchungen in Kontowährung; abweichende Währungen werden
        gezählt statt addiert. Stichtag ist das jüngste einbezogene Valutadatum.
        """
        accounts = (
            await self._session.exec(
                select(Account)
                .where(Account.mandant_id == mandant_id)
                .order_by(Account.name)
            )
        ).all()
        if not accounts:
            return AccountBalancesResponse(accounts=[], totals=[])

        aggregates = (
            await self._session.exec(
                select(
                    JournalLine.account_id,
                    JournalLine.currency,
                    func.sum(JournalLine.amount),
                    func.count(JournalLine.id),
                    func.max(JournalLine.valuta_date),
                )
                .where(
                    col(JournalLine.account_id).in_(
                        [account.id for account in accounts]
                    )
                )
                .group_by(col(JournalLine.account_id), col(JournalLine.currency))
            )
        ).all()

        by_account: dict[UUID, dict[str, tuple[Decimal, int, str | None]]] = {}
        for account_id, currency, amount_sum, line_count, last_date in aggregates:
            by_account.setdefault(account_id, {})[currency] = (
                Decimal(str(amount_sum or 0)),
                int(line_count or 0),
                last_date,
            )

        rows: list[AccountBalanceRow] = []
        totals: dict[str, dict[str, Decimal | int]] = {}
        for account in accounts:
            currency = account.currency
            per_currency = by_account.get(account.id, {})
            booked, line_count, last_date = per_currency.get(currency, (_ZERO, 0, None))
            foreign_count = sum(
                count
                for other, (_, count, _) in per_currency.items()
                if other != currency
            )
            opening = Decimal(str(account.opening_balance or 0))
            current = opening + booked

            rows.append(
                AccountBalanceRow(
                    account_id=account.id,
                    account_name=account.name,
                    iban=account.iban,
                    currency=currency,
                    is_active=account.is_active,
                    opening_balance=_as_money(opening),
                    booked_amount=_as_money(booked),
                    current_balance=_as_money(current),
                    line_count=line_count,
                    last_booking_date=last_date,
                    foreign_currency_line_count=foreign_count,
                )
            )

            total = totals.setdefault(
                currency,
                {"account_count": 0, "opening": _ZERO, "booked": _ZERO},
            )
            total["account_count"] = int(total["account_count"]) + 1
            total["opening"] = Decimal(total["opening"]) + opening
            total["booked"] = Decimal(total["booked"]) + booked

        return AccountBalancesResponse(
            accounts=rows,
            totals=[
                AccountBalanceTotal(
                    currency=currency,
                    account_count=int(total["account_count"]),
                    opening_balance=_as_money(Decimal(total["opening"])),
                    booked_amount=_as_money(Decimal(total["booked"])),
                    current_balance=_as_money(
                        Decimal(total["opening"]) + Decimal(total["booked"])
                    ),
                )
                for currency, total in sorted(totals.items())
            ],
        )

    # ─── Liquiditätsvorschau ─────────────────────────────────────────────────

    async def get_liquidity(
        self,
        mandant_id: UUID,
        scenario: Scenario = Scenario.expected,
    ) -> LiquidityResponse:
        """Kumulierter Kontostand vom laufenden Monat bis zum Ende des Prognosehorizonts.

        Startpunkt ist der aktuelle Kontostand aller Konten in Basiswährung; von dort an
        werden die Monatsprognosen aufaddiert. Für den laufenden Monat zählt nur, was über
        die bereits gebuchten Beträge hinaus erwartet wird.
        """
        base_currency = "EUR"
        balances = await self.get_account_balances(mandant_id)

        total = next(
            (entry for entry in balances.totals if entry.currency == base_currency),
            None,
        )
        start_balance = Decimal(total.current_balance) if total is not None else _ZERO
        booking_dates = [
            row.last_booking_date
            for row in balances.accounts
            if row.currency == base_currency and row.last_booking_date
        ]

        forecast_svc = ForecastService(self._session, today=self._today)
        context = await forecast_svc.build_context(mandant_id, scenario=scenario)

        # Das Unsicherheitsband und die Szenarien beantworten dieselbe Frage auf zwei
        # Arten und dürfen sich nicht überlagern: Ein Szenario verschiebt jede einzelne
        # Zelle um ihren gemessenen Fehler — das ist ein Stresstest, bei dem alle Regeln
        # gleichzeitig danebenliegen. Das Band rechnet dieselben Fehler zusammen, geht
        # dabei aber von unabhängigen Regeln aus. Beides übereinander wäre doppelt
        # gezählt, deshalb gibt es das Band nur zum Erwartungswert.
        with_band = scenario is Scenario.expected
        spreads = {
            service_id: effective.spread_used
            for service_id, effective in context.rules.items()
        }
        # Über die Zeit ist der Fehler einer Regel voll korreliert: Ein zu hoch
        # angesetzter Monatsbetrag ist jeden Monat zu hoch. Über Leistungen hinweg ist er
        # es nur teilweise — deshalb je Leistung aufsummieren und erst dann über
        # combined_uncertainty() zusammenfassen.
        cumulative_abs: dict[UUID, Decimal] = {}
        # Was gar keine Regel hat, trägt zur Prognose nichts bei — zur Unsicherheit sehr
        # wohl: Diese Buchungen bewegen den Kontostand trotzdem.
        uncovered_per_month = (
            await forecast_svc.uncovered_average_per_month(mandant_id, context)
            if with_band
            else _ZERO
        )

        months: list[LiquidityMonth] = []
        running = start_balance
        lowest = start_balance
        lowest_period: str | None = None
        lowest_low = start_balance

        for index in range(context.first_forecast_index, context.horizon_end_index + 1):
            inflow = _ZERO
            outflow = _ZERO
            for service_id in context.services:
                value = context.forecast_value(service_id, index)
                if value > _ZERO:
                    inflow += value
                elif value < _ZERO:
                    outflow += value
                # Planposten sind bekannte Beträge und tragen keine Unsicherheit.
                if (
                    with_band
                    and value != _ZERO
                    and index not in context.planned.get(service_id, {})
                ):
                    cumulative_abs[service_id] = cumulative_abs.get(
                        service_id, _ZERO
                    ) + abs(value)

            opening = running
            net = inflow + outflow
            running = opening + net
            year, month = index_to_year_month(index)
            period = f"{year:04d}-{month:02d}"

            uncertainty = _ZERO
            if with_band:
                deviations = [
                    spreads.get(service_id, _ZERO) * total
                    for service_id, total in cumulative_abs.items()
                ]
                elapsed = index - context.first_forecast_index + 1
                deviations.append(abs(uncovered_per_month) * Decimal(elapsed))
                uncertainty = combined_uncertainty(deviations)

            if running < lowest:
                lowest = running
                lowest_period = period
            lowest_low = min(lowest_low, running - uncertainty)

            months.append(
                LiquidityMonth(
                    period=period,
                    opening_balance=_as_money(opening),
                    inflow=_as_money(inflow),
                    outflow=_as_money(outflow),
                    net=_as_money(net),
                    closing_balance=_as_money(running),
                    closing_low=_as_money(running - uncertainty),
                    closing_high=_as_money(running + uncertainty),
                )
            )

        return LiquidityResponse(
            currency=base_currency,
            scenario=scenario.value,
            start_balance=_as_money(start_balance),
            as_of=max(booking_dates) if booking_dates else None,
            months=months,
            lowest_balance=_as_money(lowest),
            lowest_period=lowest_period,
            lowest_balance_low=_as_money(lowest_low),
            uncovered_average_per_month=_as_money(
                uncovered_per_month
                if with_band
                else await forecast_svc.uncovered_average_per_month(mandant_id, context)
            ),
        )

    async def get_income_expense_matrix(
        self,
        mandant_id: UUID,
        year: int,
        scenario: Scenario = Scenario.expected,
    ) -> IncomeExpenseMatrixResponse:
        base_currency = "EUR"

        service_svc = ServiceManagementService(self._session)
        await service_svc.ensure_default_groups(mandant_id)

        service_rows = (
            await self._session.exec(
                select(Service, Partner)
                .join(Partner, Partner.id == Service.partner_id)
                .where(Partner.mandant_id == mandant_id)
                .order_by(Service.name)
            )
        ).all()
        grouped_services: dict[UUID, Service] = {}
        service_section: dict[UUID, ServiceGroupSection] = {}
        service_partner_name: dict[UUID, str | None] = {}
        for service, partner in service_rows:
            section = section_for_service(service)
            if section is None:
                continue
            grouped_services[service.id] = service
            service_section[service.id] = section
            service_partner_name[service.id] = partner.display_name or partner.name

        groups_by_section = await service_svc.list_groups_by_section(mandant_id)

        assignments = (
            await self._session.exec(
                select(ServiceGroupAssignment).where(
                    ServiceGroupAssignment.mandant_id == mandant_id
                )
            )
        ).all()
        assignment_by_service: dict[UUID, ServiceGroupAssignment] = {
            assignment.service_id: assignment for assignment in assignments
        }

        # Ensure one assignment for every included service and repair wrong-section defaults.
        changed_assignments = False
        for service_id, section in service_section.items():
            service = grouped_services[service_id]
            existing_assignment = assignment_by_service.get(service_id)
            assignment = await service_svc.ensure_service_group_assignment(
                mandant_id,
                service,
                groups_by_section=groups_by_section,
                assignment=existing_assignment,
            )
            if assignment is not None and assignment is not existing_assignment:
                assignment_by_service[service_id] = assignment
                changed_assignments = True
            elif (
                existing_assignment is not None
                and assignment is not None
                and existing_assignment.service_group_id != assignment.service_group_id
            ):
                assignment_by_service[service_id] = assignment
                changed_assignments = True
        if changed_assignments:
            await self._session.commit()
            assignments = (
                await self._session.exec(
                    select(ServiceGroupAssignment).where(
                        ServiceGroupAssignment.mandant_id == mandant_id
                    )
                )
            ).all()
            assignment_by_service = {
                assignment.service_id: assignment for assignment in assignments
            }

        # Prognose nur laden, wenn das Jahr überhaupt in der Zukunft liegen kann.
        forecast_svc = ForecastService(self._session, today=self._today)
        today = self._today
        forecast_context = None
        first_forecast_month: int | None = None
        if (
            year >= today.year
            and year <= index_to_year_month(horizon_end_index(today))[0]
        ):
            forecast_context = await forecast_svc.build_context(
                mandant_id, scenario=scenario
            )
            first_forecast_month = today.month if year == today.year else 1

        # Aggregation: gross per service and month in base currency.
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)
        )
        account_ids = set(account_ids_res.all())
        if account_ids:
            line_rows = (
                await self._session.exec(
                    select(
                        JournalLineSplit.service_id,
                        JournalLine.valuta_date,
                        JournalLineSplit.amount,
                    )
                    .join(JournalLine, JournalLine.id == JournalLineSplit.journal_line_id)  # type: ignore[arg-type]
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        text("journal_lines.valuta_date LIKE :valuta_year").bindparams(
                            valuta_year=f"{year:04d}-%"
                        ),
                        JournalLine.currency == base_currency,
                    )
                )
            ).all()
            service_year_rows = (
                await self._session.exec(
                    select(
                        JournalLineSplit.service_id,
                        func.substr(JournalLine.valuta_date, 1, 4).label("year"),
                    )
                    .join(JournalLine, JournalLine.id == JournalLineSplit.journal_line_id)  # type: ignore[arg-type]
                    .where(col(JournalLine.account_id).in_(account_ids))
                )
            ).all()
            excluded_rows = (
                await self._session.exec(
                    select(JournalLine.currency, JournalLineSplit.amount)
                    .join(JournalLineSplit, JournalLineSplit.journal_line_id == JournalLine.id)  # type: ignore[arg-type]
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        text("journal_lines.valuta_date LIKE :valuta_year").bindparams(
                            valuta_year=f"{year:04d}-%"
                        ),
                        JournalLine.currency != base_currency,
                    )
                )
            ).all()
        else:
            line_rows = []
            service_year_rows = []
            excluded_rows = []

        gross_by_service_month: dict[UUID, dict[str, Decimal]] = {}
        for service_id, valuta_date, amount in line_rows:
            if service_id not in grouped_services:
                continue
            month_key = _month_key_from_valuta_date(valuta_date)
            if month_key is None:
                continue
            gross_by_service_month.setdefault(service_id, {}).setdefault(
                month_key, Decimal("0")
            )
            gross_by_service_month[service_id][month_key] += Decimal(str(amount))

        active_years_by_service: dict[UUID, set[int]] = {}
        for service_id, raw_year in service_year_rows:
            if service_id not in grouped_services:
                continue
            try:
                active_year = int(str(raw_year))
            except (TypeError, ValueError):
                continue
            active_years_by_service.setdefault(service_id, set()).add(active_year)

        excluded_count_by_section = {
            ServiceGroupSection.income: 0,
            ServiceGroupSection.expense: 0,
            ServiceGroupSection.neutral: 0,
        }
        excluded_amount_by_section = {
            ServiceGroupSection.income: Decimal("0"),
            ServiceGroupSection.expense: Decimal("0"),
            ServiceGroupSection.neutral: Decimal("0"),
        }
        if excluded_rows:
            line_rows_excluded_with_service = (
                await self._session.exec(
                    select(JournalLineSplit.service_id, JournalLineSplit.amount)
                    .join(JournalLine, JournalLine.id == JournalLineSplit.journal_line_id)  # type: ignore[arg-type]
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        text("journal_lines.valuta_date LIKE :valuta_year").bindparams(
                            valuta_year=f"{year:04d}-%"
                        ),
                        JournalLine.currency != base_currency,
                    )
                )
            ).all()
            for service_id, amount in line_rows_excluded_with_service:
                if service_id not in service_section:
                    continue
                section = service_section[service_id]
                excluded_count_by_section[section] += 1
                excluded_amount_by_section[section] += Decimal(str(amount))

        section_payload = self._matrix_sections(
            year=year,
            base_currency=base_currency,
            groups_by_section=groups_by_section,
            grouped_services=grouped_services,
            service_section=service_section,
            service_partner_name=service_partner_name,
            gross_by_service_month=gross_by_service_month,
            active_years_by_service=active_years_by_service,
            assignment_by_service=assignment_by_service,
            excluded_count_by_section=excluded_count_by_section,
            excluded_amount_by_section=excluded_amount_by_section,
            forecast_context=forecast_context,
        )

        return IncomeExpenseMatrixResponse(
            year=year,
            base_currency=base_currency,
            sections=section_payload,
            first_forecast_month=first_forecast_month,
        )

    def _matrix_sections(
        self,
        *,
        year: int,
        base_currency: str,
        groups_by_section: dict[ServiceGroupSection, list[ServiceGroup]],
        grouped_services: dict[UUID, Service],
        service_section: dict[UUID, ServiceGroupSection],
        service_partner_name: dict[UUID, str | None],
        gross_by_service_month: dict[UUID, dict[str, Decimal]],
        active_years_by_service: dict[UUID, set[int]],
        assignment_by_service: dict[UUID, ServiceGroupAssignment],
        excluded_count_by_section: dict[ServiceGroupSection, int],
        excluded_amount_by_section: dict[ServiceGroupSection, Decimal],
        forecast_context: ForecastContext | None,
    ) -> dict[str, IncomeExpenseSection]:
        """Setzt die Matrix aus den geladenen Daten zusammen.

        Herausgeloest aus get_income_expense_matrix: die Methode trug Laden und
        Zusammenbauen in 357 Zeilen mit Verschachtelungstiefe 7 — die tiefste
        Stelle des Systems, und die, in der der Rundungsfehler A2-1 sass.

        Die Parameter sind bewusst einzeln benannt statt in einem Behaelter
        gebuendelt: so ist auf einen Blick zu sehen, wie viel Zustand der
        Zusammenbau tatsaechlich braucht.
        """
        section_payload: dict[str, IncomeExpenseSection] = {}

        for section in (
            ServiceGroupSection.income,
            ServiceGroupSection.expense,
            ServiceGroupSection.neutral,
        ):
            section_groups = groups_by_section[section]
            group_rows: list[IncomeExpenseGroupRow] = []
            section_totals = _empty_cells()
            section_flags = _empty_flags()
            for group in section_groups:
                subtotal = _empty_cells()
                subtotal_flags = _empty_flags()
                services_in_group: list[IncomeExpenseServiceRow] = []

                assigned_service_ids = [
                    assignment.service_id
                    for assignment in assignment_by_service.values()
                    if assignment.service_group_id == group.id
                    and assignment.service_id in grouped_services
                ]
                active_years_in_group = sorted(
                    {
                        active_year
                        for service_id in assigned_service_ids
                        for active_year in active_years_by_service.get(
                            service_id, set()
                        )
                    }
                )
                for service_id in sorted(
                    assigned_service_ids,
                    key=lambda item: grouped_services[item].name.lower(),
                ):
                    service = grouped_services[service_id]
                    if service_section[service_id] != section:
                        continue

                    service_cells, service_flags = self._service_cells(
                        service=service,
                        service_id=service_id,
                        year=year,
                        gross_by_service_month=gross_by_service_month,
                        forecast_context=forecast_context,
                    )

                    for cell_key in ["year_total", *MONTH_KEYS]:
                        subtotal[cell_key]["gross"] += service_cells[cell_key]["gross"]
                        subtotal[cell_key]["net"] += service_cells[cell_key]["net"]
                        subtotal_flags[cell_key] = (
                            subtotal_flags[cell_key] or service_flags[cell_key]
                        )

                        section_totals[cell_key]["gross"] += service_cells[cell_key][
                            "gross"
                        ]
                        section_totals[cell_key]["net"] += service_cells[cell_key][
                            "net"
                        ]
                        section_flags[cell_key] = (
                            section_flags[cell_key] or service_flags[cell_key]
                        )

                    effective = (
                        forecast_context.rules.get(service_id)
                        if forecast_context
                        else None
                    )
                    services_in_group.append(
                        IncomeExpenseServiceRow(
                            service_id=service.id,
                            partner_id=service.partner_id,
                            service_name=service.name,
                            partner_name=service_partner_name.get(service.id),
                            service_type=service.service_type,
                            erfolgsneutral=service.erfolgsneutral,
                            cells=_to_cells_payload(service_cells, service_flags),
                            forecast_rule=(
                                effective.rule.rule_type.value if effective else None
                            ),
                            forecast_mode=effective.mode.value if effective else None,
                            forecast_confidence=(
                                effective.rule.confidence.value
                                if effective and effective.is_active
                                else None
                            ),
                            forecast_reason=effective.reason if effective else None,
                        )
                    )

                group_rows.append(
                    IncomeExpenseGroupRow(
                        group_id=group.id,
                        group_name=group.name,
                        sort_order=group.sort_order,
                        collapsed=False,
                        assigned_service_count=len(assigned_service_ids),
                        active_years=active_years_in_group,
                        subtotal_cells=_to_cells_payload(subtotal, subtotal_flags),
                        services=services_in_group,
                    )
                )

            section_payload[section.value] = IncomeExpenseSection(
                currency=base_currency,
                excluded_currency_count=excluded_count_by_section[section],
                excluded_currency_amount_gross=_as_money(
                    excluded_amount_by_section[section]
                ),
                groups=group_rows,
                totals=_to_cells_payload(section_totals, section_flags),
            )

        return section_payload

    def _service_cells(
        self,
        *,
        service: Service,
        service_id: UUID,
        year: int,
        gross_by_service_month: dict[UUID, dict[str, Decimal]],
        forecast_context: ForecastContext | None,
    ) -> tuple[dict[str, dict[str, Decimal]], dict[str, bool]]:
        """Fuellt die zwoelf Monats- und die Jahreszelle einer Leistung.

        Herausgeloest, weil die Monatsschleife samt ihrer Prognose-Fallunter-
        scheidungen die beiden tiefsten Ebenen von _matrix_sections stellte.
        """
        service_cells = _empty_cells()
        service_flags = _empty_flags()
        monthly_gross = gross_by_service_month.get(service_id, {})
        for month_number, month_key in enumerate(MONTH_KEYS, start=1):
            gross_value = monthly_gross.get(month_key, Decimal("0"))
            if forecast_context is not None:
                index = month_index(year, month_number)
                gross_value += forecast_context.forecast_value(service_id, index)
                # Künftige Monate sind immer Prognose — auch dann, wenn mangels
                # Historie keine Zahl entsteht. Der laufende Monat nur insoweit,
                # als noch etwas zum Gebuchten hinzukommt.
                if index > forecast_context.first_forecast_index:
                    service_flags[month_key] = (
                        index <= forecast_context.horizon_end_index
                    )
                elif index == forecast_context.first_forecast_index:
                    service_flags[month_key] = gross_value != monthly_gross.get(
                        month_key, Decimal("0")
                    )
            service_cells[month_key]["gross"] = gross_value
            service_cells["year_total"]["gross"] += gross_value
            service_flags["year_total"] = (
                service_flags["year_total"] or service_flags[month_key]
            )

        # Netto wird hier — und nur hier — gerundet. Alles darueber
        # entsteht durch Summieren dieser Werte, damit sich die Anzeige
        # in beide Richtungen addiert: die Monate zur Jahreszelle und die
        # Leistungszeilen zur Zwischen- und Gesamtsumme. Der Preis ist,
        # dass die Jahreszelle nicht exakt jahresbrutto/divisor ist,
        # sondern um wenige Cent davon abweichen kann. Das ist der
        # bewusste Tausch: eine Tabelle, die aufgeht, gegen eine
        # Jahressumme, die niemand nachrechnet.
        tax_rate = Decimal(str(service.tax_rate))
        divisor = Decimal("1") + (tax_rate / Decimal("100"))
        for month_key in MONTH_KEYS:
            gross_value = service_cells[month_key]["gross"]
            service_cells[month_key]["net"] = (
                _round_money(gross_value / divisor)
                if divisor != Decimal("0")
                else gross_value
            )
        service_cells["year_total"]["net"] = sum(
            (service_cells[month_key]["net"] for month_key in MONTH_KEYS),
            Decimal("0"),
        )

        return service_cells, service_flags

    # ─── Bulk-assign ─────────────────────────────────────────────────────────

    async def bulk_assign(
        self,
        mandant_id: UUID,
        actor_id: UUID,
        line_ids: list[UUID],
        partner_id: UUID,
    ) -> BulkAssignResponse:
        if not line_ids:
            return BulkAssignResponse(assigned=0, skipped=0)

        # Security: resolve all mandant accounts once
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        lines_res = await self._session.exec(
            select(JournalLine).where(col(JournalLine.id).in_(line_ids))
        )
        lines = lines_res.all()

        # Reject request if any requested line belongs to a different mandant
        foreign = [ln for ln in lines if ln.account_id not in mandant_account_ids]
        if foreign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One or more journal lines do not belong to this mandant",
            )

        assigned = 0
        skipped = 0
        changed_lines: list[JournalLine] = []
        for ln in lines:
            if ln.partner_id == partner_id:
                skipped += 1
                continue
            changed_lines.append(ln)
            assigned += 1

        service_svc = ServiceManagementService(self._session)
        await service_svc.prepare_lines_for_partner_change(
            mandant_id, changed_lines, partner_id
        )

        # Single audit log entry for the whole operation
        entry = AuditLog(
            mandant_id=mandant_id,
            event_type="journal.bulk_assign",
            actor_id=actor_id,
            payload={
                "partner_id": str(partner_id),
                "line_ids": [str(lid) for lid in line_ids],
                "assigned": assigned,
                "skipped": skipped,
            },
        )
        self._session.add(entry)

        if assigned > 0:
            await service_svc.revalidate_partner_lines(partner_id)
        else:
            await self._session.commit()

        log.info(
            "journal_bulk_assigned",
            mandant_id=str(mandant_id),
            partner_id=str(partner_id),
            assigned=assigned,
        )
        return BulkAssignResponse(assigned=assigned, skipped=skipped)

    async def assign_service(
        self,
        mandant_id: UUID,
        actor_id: UUID,
        line_id: UUID,
        service_id: UUID,
    ) -> JournalLineResponse:
        line = await self._session.get(JournalLine, line_id)
        if line is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found"
            )

        account = await self._session.get(Account, line.account_id)
        if account is None or account.mandant_id != mandant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Journal line does not belong to this mandant",
            )

        service_svc = ServiceManagementService(self._session)
        await service_svc.manually_assign_journal_line(mandant_id, line, service_id)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="journal.service_assigned",
                actor_id=actor_id,
                payload={
                    "journal_line_id": str(line.id),
                    "service_id": str(service_id),
                },
            )
        )
        await self._session.commit()
        await self._session.refresh(line)

        partner_name = None
        if line.partner_id is not None:
            partner = await self._session.get(Partner, line.partner_id)
            if partner is not None:
                partner_name = partner.display_name or partner.name

        splits = (
            await self._session.exec(
                select(JournalLineSplit).where(
                    JournalLineSplit.journal_line_id == line.id
                )
            )
        ).all()
        split_svc_ids = {sp.service_id for sp in splits}
        service_names_map: dict = {}
        if split_svc_ids:
            s_res = await self._session.exec(
                select(Service.id, Service.name).where(
                    col(Service.id).in_(split_svc_ids)
                )
            )
            service_names_map = {sid: sname for sid, sname in s_res.all()}

        return JournalLineResponse(
            **{
                **{
                    key: value
                    for key, value in line.model_dump().items()
                    if key != "unmapped_data"
                },
                "unmapped_data": _sanitize_unmapped_data(line.unmapped_data),
            },
            splits=[
                {
                    "service_id": sp.service_id,
                    "service_name": service_names_map.get(sp.service_id),
                    "amount": sp.amount,
                    "assignment_mode": sp.assignment_mode,
                    "amount_consistency_ok": sp.amount_consistency_ok,
                }
                for sp in splits
            ],
            partner_name=partner_name,
        )
