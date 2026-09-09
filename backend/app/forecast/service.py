"""Lädt die Historie je Leistung, bildet Profile und projiziert künftige Monate.

Prognosewerte werden bewusst nicht persistiert: Mit jedem Import ändert sich die Historie,
gespeicherte Werte wären sofort veraltet. Die Berechnung ist billig genug, um bei jedem
Aufruf zu laufen.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.forecast.backtest import BacktestReport, applied_profile, run_backtest
from app.forecast.models import (
    ForecastMode,
    ForecastPlannedItem,
    ForecastSnapshot,
    ServiceForecastRule,
)
from app.forecast.profiler import (
    ForecastProfile,
    build_profile,
    index_to_year_month,
    median,
    month_index,
)
from app.forecast.rules import EffectiveRule, Scenario, projected_value, resolve_rule
from app.forecast.schemas import (
    BacktestCandidateResponse,
    BacktestResponse,
    CreatePlannedItemRequest,
    CreateSnapshotRequest,
    ForecastOverviewResponse,
    ForecastPreviewMonth,
    ForecastRuleResponse,
    ForecastServiceOverviewRow,
    PlannedItemResponse,
    PlannedItemStatus,
    SnapshotDetail,
    SnapshotMonthComparison,
    SnapshotSummary,
    UpdateForecastRuleRequest,
    UpdatePlannedItemRequest,
)
from app.imports.models import JournalLine, JournalLineSplit
from app.journal.schemas import LiquidityResponse
from app.partners.models import Partner
from app.services.models import Service, section_for_service
from app.tenants.models import Account

BASE_CURRENCY = "EUR"

_ZERO = Decimal("0")


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _ratio(value: Decimal | None) -> str | None:
    """Anteile auf vier Nachkommastellen — 0,0834 statt einer Zahl voller Rundungsreste."""
    if value is None:
        return None
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _period_of(index: int) -> str:
    year, month = index_to_year_month(index)
    return f"{year:04d}-{month:02d}"


def backtest_response(report: BacktestReport, window_end: int) -> BacktestResponse:
    """Der Rückvergleich für die Oberfläche — die Kandidatentabelle ist die Begründung."""
    winner_key = report.winner.key if report.winner else None
    return BacktestResponse(
        ran=report.ran,
        reason=report.reason,
        holdout_months=report.holdout_months,
        holdout_from=(
            _period_of(report.train_end_index + 1)
            if report.train_end_index is not None
            else None
        ),
        holdout_to=_period_of(window_end) if report.ran else None,
        actual_volume=_money(report.actual_volume),
        relative_error=_ratio(report.relative_error),
        spread=_ratio(report.spread),
        beats_baseline=report.beats_baseline,
        replaced_detected=report.replaced_detected,
        service_stopped=report.service_stopped,
        candidates=[
            BacktestCandidateResponse(
                key=score.key,
                label=score.label,
                mae=_money(score.mae),
                level_error=_money(score.level_error),
                score=_money(score.score),
                is_baseline=score.is_baseline,
                is_winner=score.key == winner_key,
            )
            for score in report.scores
        ],
    )


def horizon_end_index(today: date) -> int:
    """Letzter Prognosemonat: Dezember des Folgejahres."""
    return month_index(today.year + 1, 12)


def remaining_for_current_month(forecast: Decimal, actual: Decimal) -> Decimal:
    """Noch nicht gebuchter Teil der Monatsprognose.

    Der laufende Monat ist unvollständig: Ein Teil ist schon gebucht, der Rest steht aus.
    Übersteigt das Gebuchte die Prognose bereits, kommt nichts mehr dazu — sonst würde der
    Monat doppelt gezählt.
    """
    if forecast == _ZERO:
        return _ZERO
    remainder = forecast - actual
    if (remainder > _ZERO) != (forecast > _ZERO):
        return _ZERO
    return remainder


@dataclass(frozen=True)
class ForecastContext:
    """Alles, was für Matrix und Liquiditätskurve gebraucht wird — einmal geladen."""

    today: date
    first_forecast_index: int
    history_end_index: int
    horizon_end_index: int
    scenario: Scenario
    services: dict[UUID, Service]
    #: Das Profil, wie es nach dem Rückvergleich gilt — die Regel darin wird gerechnet.
    profiles: dict[UUID, ForecastProfile]
    #: Was der Profiler ohne Rückvergleich vorgeschlagen hätte — bleibt sichtbar.
    detected: dict[UUID, ForecastProfile]
    backtests: dict[UUID, BacktestReport]
    rules: dict[UUID, EffectiveRule]
    actuals: dict[UUID, dict[int, Decimal]]
    planned: dict[UUID, dict[int, Decimal]]

    def forecast_value(self, service_id: UUID, index: int) -> Decimal:
        """Prognostizierter Zusatzbetrag für einen Monat — 0 für Vergangenheit."""
        if index < self.first_forecast_index or index > self.horizon_end_index:
            return _ZERO

        planned = self.planned.get(service_id, {}).get(index)
        if planned is not None:
            # Bekannt schlägt geschätzt: kein Modifikator, keine Szenario-Bandbreite.
            projected = planned
        else:
            effective = self.rules.get(service_id)
            if effective is None:
                return _ZERO
            projected = projected_value(
                effective,
                index,
                history=self.actuals.get(service_id, {}),
                scenario=self.scenario,
            )

        if index == self.first_forecast_index:
            actual = self.actuals.get(service_id, {}).get(index, _ZERO)
            return remaining_for_current_month(projected, actual)
        return projected

    def has_rule(self, service_id: UUID) -> bool:
        """Ob diese Leistung überhaupt etwas zur Prognose beiträgt."""
        if self.planned.get(service_id):
            return True
        effective = self.rules.get(service_id)
        return effective is not None and effective.is_active


class ForecastService:
    def __init__(self, session: AsyncSession, *, today: date | None = None) -> None:
        self._session = session
        self._today = today or date.today()

    @property
    def today(self) -> date:
        return self._today

    async def build_context(
        self,
        mandant_id: UUID,
        *,
        scenario: Scenario = Scenario.expected,
    ) -> ForecastContext:
        first_forecast_index = month_index(self._today.year, self._today.month)
        history_end_index = first_forecast_index - 1

        services = await self._load_forecastable_services(mandant_id)
        actuals = await self._load_monthly_series(mandant_id, set(services))
        overrides = await self.load_overrides(mandant_id)
        planned = await self.load_planned_items(mandant_id)

        profiles: dict[UUID, ForecastProfile] = {}
        detected: dict[UUID, ForecastProfile] = {}
        backtests: dict[UUID, BacktestReport] = {}
        rules: dict[UUID, EffectiveRule] = {}
        for service_id, service in services.items():
            history = actuals.get(service_id, {})
            profile = build_profile(
                history,
                window_end=history_end_index,
                valid_from=service.valid_from,
                valid_to=service.valid_to,
            )
            report = run_backtest(
                history,
                window_end=history_end_index,
                profile=profile,
                valid_from=service.valid_from,
                valid_to=service.valid_to,
            )
            detected[service_id] = profile
            backtests[service_id] = report
            profile = applied_profile(profile, report)
            profiles[service_id] = profile
            rules[service_id] = resolve_rule(
                profile,
                overrides.get(service_id),
                history=history,
                window_end=history_end_index,
                valid_from=service.valid_from,
                valid_to=service.valid_to,
                measured_spread=report.spread,
            )

        return ForecastContext(
            today=self._today,
            first_forecast_index=first_forecast_index,
            history_end_index=history_end_index,
            horizon_end_index=horizon_end_index(self._today),
            scenario=scenario,
            services=services,
            profiles=profiles,
            detected=detected,
            backtests=backtests,
            rules=rules,
            actuals=actuals,
            planned=planned,
        )

    async def load_overrides(self, mandant_id: UUID) -> dict[UUID, ServiceForecastRule]:
        rows = (
            await self._session.exec(
                select(ServiceForecastRule).where(
                    ServiceForecastRule.mandant_id == mandant_id
                )
            )
        ).all()
        return {row.service_id: row for row in rows}

    async def load_planned_items(
        self, mandant_id: UUID
    ) -> dict[UUID, dict[int, Decimal]]:
        """Planposten je Leistung und Monat. Mehrere Posten im selben Monat summieren sich."""
        rows = (
            await self._session.exec(
                select(ForecastPlannedItem).where(
                    ForecastPlannedItem.mandant_id == mandant_id
                )
            )
        ).all()
        planned: dict[UUID, dict[int, Decimal]] = {}
        for row in rows:
            index = _period_to_index(row.period)
            if index is None:
                continue
            months = planned.setdefault(row.service_id, {})
            months[index] = months.get(index, _ZERO) + Decimal(str(row.amount))
        return planned

    async def uncovered_average_per_month(
        self,
        mandant_id: UUID,
        context: ForecastContext,
    ) -> Decimal:
        """Monatsdurchschnitt des Volumens, das die Prognose nicht abdeckt.

        Drei Gruppen fallen heraus: Buchungen ohne Split, interne Umbuchungen und
        unklassifizierte Leistungen (beide nicht in der Matrix) sowie Leistungen, für die
        mangels Historie keine Regel zustande kam. Gerade die letzte Gruppe trifft
        unregelmäßige Einnahmen häufiger als regelmäßige Ausgaben — ohne diesen Wert wäre
        die Kurve still zu pessimistisch.
        """
        account_ids = await self._account_ids(mandant_id)
        if not account_ids:
            return _ZERO

        window = 12
        history_end = month_index(self._today.year, self._today.month) - 1
        first_year, first_month = divmod(history_end - window + 1, 12)
        start_period = f"{first_year:04d}-{first_month + 1:02d}"
        end_year, end_month = divmod(history_end, 12)
        end_period = f"{end_year:04d}-{end_month + 1:02d}"

        total_all = await self._session.scalar(
            select(func.sum(JournalLine.amount)).where(
                col(JournalLine.account_id).in_(account_ids),
                JournalLine.currency == BASE_CURRENCY,
                func.substr(JournalLine.valuta_date, 1, 7) >= start_period,
                func.substr(JournalLine.valuta_date, 1, 7) <= end_period,
            )
        )

        projected_service_ids = {
            service_id
            for service_id in context.services
            if context.has_rule(service_id)
        }
        if projected_service_ids:
            total_covered = await self._session.scalar(
                select(func.sum(JournalLineSplit.amount))
                .join(JournalLine, JournalLine.id == JournalLineSplit.journal_line_id)  # type: ignore[arg-type]
                .where(
                    col(JournalLine.account_id).in_(account_ids),
                    JournalLine.currency == BASE_CURRENCY,
                    col(JournalLineSplit.service_id).in_(projected_service_ids),
                    func.substr(JournalLine.valuta_date, 1, 7) >= start_period,
                    func.substr(JournalLine.valuta_date, 1, 7) <= end_period,
                )
            )
        else:
            total_covered = None

        uncovered = Decimal(str(total_all or 0)) - Decimal(str(total_covered or 0))
        return uncovered / Decimal(window)

    # ─── Verwaltung: Regeln je Leistung ──────────────────────────────────────

    PREVIEW_MONTHS = 12

    def _period(self, index: int) -> str:
        return _period_of(index)

    def _preview(
        self, context: ForecastContext, service_id: UUID
    ) -> list[ForecastPreviewMonth]:
        planned = context.planned.get(service_id, {})
        return [
            ForecastPreviewMonth(
                period=self._period(index),
                amount=_money(context.forecast_value(service_id, index)),
                is_planned=index in planned,
            )
            for index in range(
                context.first_forecast_index,
                min(
                    context.first_forecast_index + self.PREVIEW_MONTHS,
                    context.horizon_end_index + 1,
                ),
            )
        ]

    async def _partner_names(self, mandant_id: UUID) -> dict[UUID, str | None]:
        rows = (
            await self._session.exec(
                select(Partner.id, Partner.display_name, Partner.name).where(
                    Partner.mandant_id == mandant_id
                )
            )
        ).all()
        return {row[0]: row[1] or row[2] for row in rows}

    def _require_service(self, context: ForecastContext, service_id: UUID) -> Service:
        service = context.services.get(service_id)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or not part of the forecast",
            )
        return service

    async def get_rule(
        self, mandant_id: UUID, service_id: UUID
    ) -> ForecastRuleResponse:
        context = await self.build_context(mandant_id)
        service = self._require_service(context, service_id)
        override = (await self.load_overrides(mandant_id)).get(service_id)
        # Was der Profiler ohne Rückvergleich sah, bleibt sichtbar — sonst wäre nicht
        # nachvollziehbar, was die Messung geändert hat.
        profile = context.detected[service_id]
        report = context.backtests[service_id]
        effective = context.rules[service_id]
        partner_names = await self._partner_names(mandant_id)

        return ForecastRuleResponse(
            service_id=service_id,
            service_name=service.name,
            partner_name=partner_names.get(service.partner_id),
            mode=effective.mode,
            rule_type=override.rule_type if override else None,
            params=(
                override.params
                if override and isinstance(override.params, dict)
                else None
            ),
            adjustment_pct=effective.adjustment_pct,
            shift_months=effective.shift_months,
            detected_cadence=profile.cadence.value,
            detected_rule_type=profile.rule.rule_type.value,
            detected_reason=profile.rule.reason,
            occurrence_count=profile.occurrence_count,
            median_amount=_money(profile.median_amount),
            effective_rule_type=effective.rule.rule_type.value,
            effective_reason=effective.reason,
            confidence=effective.rule.confidence.value if effective.is_active else None,
            preview=self._preview(context, service_id),
            backtest=backtest_response(report, context.history_end_index),
        )

    async def set_rule(
        self,
        mandant_id: UUID,
        service_id: UUID,
        data: UpdateForecastRuleRequest,
        actor_id: UUID | None = None,
    ) -> ForecastRuleResponse:
        context = await self.build_context(mandant_id)
        self._require_service(context, service_id)

        existing = (await self.load_overrides(mandant_id)).get(service_id)
        if existing is None:
            existing = ServiceForecastRule(mandant_id=mandant_id, service_id=service_id)
            self._session.add(existing)

        existing.mode = data.mode.value
        existing.rule_type = (
            data.rule_type if data.mode is ForecastMode.manual else None
        )
        existing.params = data.params if data.mode is ForecastMode.manual else None
        existing.adjustment_pct = data.adjustment_pct
        existing.shift_months = data.shift_months
        existing.updated_by = actor_id
        existing.updated_at = datetime.now(UTC)
        await self._session.commit()

        return await self.get_rule(mandant_id, service_id)

    async def delete_rule(
        self, mandant_id: UUID, service_id: UUID
    ) -> ForecastRuleResponse:
        """Setzt die Leistung auf den automatischen Vorschlag zurück."""
        override = (await self.load_overrides(mandant_id)).get(service_id)
        if override is not None:
            await self._session.delete(override)
            await self._session.commit()
        return await self.get_rule(mandant_id, service_id)

    # ─── Verwaltung: Übersicht ───────────────────────────────────────────────

    async def overview(
        self,
        mandant_id: UUID,
        *,
        only_without_rule: bool = False,
        search: str = "",
    ) -> ForecastOverviewResponse:
        context = await self.build_context(mandant_id)
        partner_names = await self._partner_names(mandant_id)

        rows: list[ForecastServiceOverviewRow] = []
        without_rule = 0
        customised = 0
        backtested = 0
        replaced = 0
        stopped = 0
        weak = 0
        relative_errors: list[Decimal] = []
        for service_id, service in context.services.items():
            effective = context.rules[service_id]
            profile = context.profiles[service_id]
            report = context.backtests[service_id]
            has_rule = context.has_rule(service_id)
            planned_count = len(context.planned.get(service_id, {}))
            is_customised = (
                effective.mode is not ForecastMode.auto
                or effective.adjustment_pct != _ZERO
                or effective.shift_months > 0
                or planned_count > 0
            )
            if not has_rule:
                without_rule += 1
            customised += is_customised
            if report.ran:
                backtested += 1
                replaced += report.replaced_detected
                stopped += report.service_stopped
                # Eine abgeschaltete Leistung ist behoben, nicht schwach.
                weak += not report.beats_baseline and not report.service_stopped
                if report.relative_error is not None:
                    relative_errors.append(report.relative_error)
            if only_without_rule and has_rule:
                continue

            partner_name = partner_names.get(service.partner_id)
            if search:
                haystack = f"{service.name} {partner_name or ''}".lower()
                if search.lower() not in haystack:
                    continue

            horizon = min(
                context.first_forecast_index + self.PREVIEW_MONTHS,
                context.horizon_end_index + 1,
            )
            next_12 = sum(
                (
                    context.forecast_value(service_id, index)
                    for index in range(context.first_forecast_index, horizon)
                ),
                _ZERO,
            )
            section = section_for_service(service)

            rows.append(
                ForecastServiceOverviewRow(
                    service_id=service_id,
                    service_name=service.name,
                    partner_id=service.partner_id,
                    partner_name=partner_name,
                    section=section.value if section else "",
                    mode=effective.mode,
                    effective_rule_type=effective.rule.rule_type.value,
                    effective_reason=effective.reason,
                    confidence=(
                        effective.rule.confidence.value if effective.is_active else None
                    ),
                    detected_cadence=profile.cadence.value,
                    occurrence_count=profile.occurrence_count,
                    last_booking_period=(
                        self._period(profile.last_index) if profile.last_index else None
                    ),
                    next_12_months=_money(next_12),
                    planned_item_count=planned_count,
                    adjustment_pct=effective.adjustment_pct,
                    shift_months=effective.shift_months,
                    customised=is_customised,
                    relative_error=_ratio(report.relative_error),
                    backtest_ran=report.ran,
                    beats_baseline=report.beats_baseline,
                    replaced_detected=report.replaced_detected,
                    service_stopped=report.service_stopped,
                )
            )

        rows.sort(key=lambda row: abs(Decimal(row.next_12_months)), reverse=True)
        return ForecastOverviewResponse(
            services=rows,
            total=len(rows),
            without_rule=without_rule,
            customised=customised,
            backtested=backtested,
            replaced_by_backtest=replaced,
            stopped_by_backtest=stopped,
            weak_forecasts=weak,
            median_relative_error=(
                _ratio(median(relative_errors)) if relative_errors else None
            ),
        )

    # ─── Verwaltung: Planposten ──────────────────────────────────────────────

    async def _planned_item(
        self, mandant_id: UUID, item_id: UUID
    ) -> ForecastPlannedItem:
        item = await self._session.get(ForecastPlannedItem, item_id)
        if item is None or item.mandant_id != mandant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Planned item not found"
            )
        return item

    async def _to_planned_response(
        self,
        item: ForecastPlannedItem,
        services: dict[UUID, Service],
        partner_names: dict[UUID, str | None],
        states: dict[UUID, tuple[PlannedItemStatus, Decimal]] | None = None,
    ) -> PlannedItemResponse:
        service = services.get(item.service_id)
        response = PlannedItemResponse.model_validate(item)
        response.service_name = service.name if service else None
        response.partner_name = (
            partner_names.get(service.partner_id) if service else None
        )
        if states is None:
            states = await self._planned_states([item])
        status, remaining = states.get(
            item.id, (PlannedItemStatus.active, Decimal(str(item.amount)))
        )
        response.status = status
        response.remaining_in_month = _money(remaining)
        return response

    async def _planned_states(
        self,
        items: list[ForecastPlannedItem],
    ) -> dict[UUID, tuple[PlannedItemStatus, Decimal]]:
        """Wieviel jeder Posten noch beiträgt — dieselbe Rechnung wie in der Projektion.

        Nur der laufende Monat braucht die Ist-Beträge; alles davor ist ohnehin
        wirkungslos, alles danach voll wirksam. Posten desselben Monats wirken gemeinsam
        gegen das Ist, deshalb wird ihr Status je Monat und nicht je Posten bestimmt.
        """
        current = month_index(self._today.year, self._today.month)
        totals: dict[UUID, Decimal] = {}
        for item in items:
            if _period_to_index(item.period) == current:
                totals[item.service_id] = totals.get(item.service_id, _ZERO) + Decimal(
                    str(item.amount)
                )

        actuals = await self._current_month_actuals(set(totals)) if totals else {}

        states: dict[UUID, tuple[PlannedItemStatus, Decimal]] = {}
        for item in items:
            index = _period_to_index(item.period)
            amount = Decimal(str(item.amount))
            if index is None or index < current:
                states[item.id] = (PlannedItemStatus.expired, _ZERO)
            elif index > current:
                states[item.id] = (PlannedItemStatus.active, amount)
            else:
                planned = totals.get(item.service_id, amount)
                remaining = remaining_for_current_month(
                    planned, actuals.get(item.service_id, _ZERO)
                )
                if remaining == _ZERO:
                    states[item.id] = (PlannedItemStatus.used, _ZERO)
                elif remaining != planned:
                    states[item.id] = (PlannedItemStatus.partly_used, remaining)
                else:
                    states[item.id] = (PlannedItemStatus.active, remaining)
        return states

    async def _current_month_actuals(
        self,
        service_ids: set[UUID],
    ) -> dict[UUID, Decimal]:
        """Ist-Beträge des laufenden Monats — gezielt statt über den ganzen Kontext."""
        if not service_ids:
            return {}
        period = f"{self._today.year:04d}-{self._today.month:02d}"
        rows = (
            await self._session.exec(
                select(JournalLineSplit.service_id, func.sum(JournalLineSplit.amount))
                .join(JournalLine, JournalLine.id == JournalLineSplit.journal_line_id)  # type: ignore[arg-type]
                .where(
                    col(JournalLineSplit.service_id).in_(service_ids),
                    JournalLine.currency == BASE_CURRENCY,
                    func.substr(JournalLine.valuta_date, 1, 7) == period,
                )
                .group_by(col(JournalLineSplit.service_id))
            )
        ).all()
        return {service_id: Decimal(str(total or 0)) for service_id, total in rows}

    async def list_planned_items(
        self,
        mandant_id: UUID,
        service_id: UUID | None = None,
    ) -> list[PlannedItemResponse]:
        query = select(ForecastPlannedItem).where(
            ForecastPlannedItem.mandant_id == mandant_id
        )
        if service_id is not None:
            query = query.where(ForecastPlannedItem.service_id == service_id)
        rows = list(
            (await self._session.exec(query.order_by(ForecastPlannedItem.period))).all()
        )

        services = await self._load_forecastable_services(mandant_id)
        partner_names = await self._partner_names(mandant_id)
        states = await self._planned_states(rows)
        items = [
            await self._to_planned_response(row, services, partner_names, states)
            for row in rows
        ]

        # Was noch wirkt, gehört nach oben; Abgelaufenes ans Ende, das Jüngste zuerst.
        def order(item: PlannedItemResponse) -> tuple[int, int]:
            rank = _PLANNED_SORT_RANK[item.status]
            index = _period_to_index(item.period) or 0
            return (rank, -index if rank == 2 else index)

        items.sort(key=order)
        return items

    async def create_planned_item(
        self,
        mandant_id: UUID,
        data: CreatePlannedItemRequest,
        actor_id: UUID | None = None,
    ) -> PlannedItemResponse:
        services = await self._load_forecastable_services(mandant_id)
        if data.service_id not in services:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or not part of the forecast",
            )
        item = ForecastPlannedItem(
            mandant_id=mandant_id,
            service_id=data.service_id,
            period=data.period,
            amount=data.amount,
            note=data.note,
            created_by=actor_id,
        )
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return await self._to_planned_response(
            item, services, await self._partner_names(mandant_id)
        )

    async def update_planned_item(
        self,
        mandant_id: UUID,
        item_id: UUID,
        data: UpdatePlannedItemRequest,
    ) -> PlannedItemResponse:
        item = await self._planned_item(mandant_id, item_id)
        if data.period is not None:
            item.period = data.period
        if data.amount is not None:
            item.amount = data.amount
        if data.note is not None:
            item.note = data.note or None
        item.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(item)
        return await self._to_planned_response(
            item,
            await self._load_forecastable_services(mandant_id),
            await self._partner_names(mandant_id),
        )

    async def delete_planned_item(self, mandant_id: UUID, item_id: UUID) -> None:
        item = await self._planned_item(mandant_id, item_id)
        await self._session.delete(item)
        await self._session.commit()

    # ─── Plan-Ist-Snapshots ──────────────────────────────────────────────────

    async def create_snapshot(
        self,
        mandant_id: UUID,
        data: CreateSnapshotRequest,
        liquidity: LiquidityResponse,
        actor_id: UUID | None = None,
    ) -> SnapshotDetail:
        """Friert die aktuelle Liquiditätsprognose ein.

        Die Prognose kommt fertig herein, statt hier ein zweites Mal gerechnet zu werden —
        so ist garantiert, dass der Snapshot exakt das festhält, was die Oberfläche im
        selben Moment gezeigt hat.
        """
        snapshot = ForecastSnapshot(
            mandant_id=mandant_id,
            label=data.label or None,
            scenario=liquidity.scenario,
            as_of=self._today.isoformat(),
            currency=liquidity.currency,
            start_balance=Decimal(liquidity.start_balance),
            months=[
                {
                    "period": month.period,
                    "inflow": month.inflow,
                    "outflow": month.outflow,
                    "net": month.net,
                    "closing_balance": month.closing_balance,
                }
                for month in liquidity.months
            ],
            created_by=actor_id,
        )
        self._session.add(snapshot)
        await self._session.commit()
        await self._session.refresh(snapshot)
        return await self.get_snapshot(mandant_id, snapshot.id)

    async def list_snapshots(self, mandant_id: UUID) -> list[SnapshotSummary]:
        rows = (
            await self._session.exec(
                select(ForecastSnapshot)
                .where(ForecastSnapshot.mandant_id == mandant_id)
                .order_by(col(ForecastSnapshot.created_at).desc())
            )
        ).all()
        return [(await self._compare(mandant_id, row)) for row in rows]

    async def get_snapshot(self, mandant_id: UUID, snapshot_id: UUID) -> SnapshotDetail:
        snapshot = await self._session.get(ForecastSnapshot, snapshot_id)
        if snapshot is None or snapshot.mandant_id != mandant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found"
            )
        return await self._compare(mandant_id, snapshot, with_months=True)

    async def delete_snapshot(self, mandant_id: UUID, snapshot_id: UUID) -> None:
        snapshot = await self._session.get(ForecastSnapshot, snapshot_id)
        if snapshot is None or snapshot.mandant_id != mandant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found"
            )
        await self._session.delete(snapshot)
        await self._session.commit()

    async def _compare(
        self,
        mandant_id: UUID,
        snapshot: ForecastSnapshot,
        *,
        with_months: bool = False,
    ) -> SnapshotDetail:
        """Stellt dem eingefrorenen Plan die tatsächlichen Kontobewegungen gegenüber.

        Verglichen wird gegen *alle* Buchungen in Basiswährung, nicht nur gegen die
        prognostizierten Leistungen: Der Snapshot sagt einen Kontostand voraus, und den
        bewegt jede Buchung — auch die, für die es nie eine Regel gab. Alles andere wäre
        eine geschönte Messung.
        """
        stored = snapshot.months if isinstance(snapshot.months, list) else []
        actuals = await self._actual_net_by_period(mandant_id, since=snapshot.as_of)
        current_period = f"{self._today.year:04d}-{self._today.month:02d}"

        months: list[SnapshotMonthComparison] = []
        running = Decimal(str(snapshot.start_balance))
        elapsed = 0
        deviations: list[Decimal] = []
        latest_deviation: Decimal | None = None

        for entry in stored:
            period = str(entry.get("period", ""))
            planned_net = Decimal(str(entry.get("net", "0")))
            planned_closing = Decimal(str(entry.get("closing_balance", "0")))

            if period > current_period:
                months.append(
                    SnapshotMonthComparison(
                        period=period,
                        planned_net=_money(planned_net),
                        planned_closing=_money(planned_closing),
                    )
                )
                continue

            actual_net = actuals.get(period, _ZERO)
            running += actual_net
            deviation = running - planned_closing
            complete = period < current_period
            # Der laufende Monat wird zwar angezeigt, zählt aber nicht in die Messung:
            # Er ist erst halb gebucht und würde die Abweichung immer zu groß aussehen
            # lassen.
            if complete:
                elapsed += 1
                deviations.append(abs(deviation))
                latest_deviation = deviation

            months.append(
                SnapshotMonthComparison(
                    period=period,
                    planned_net=_money(planned_net),
                    planned_closing=_money(planned_closing),
                    actual_net=_money(actual_net),
                    actual_closing=_money(running),
                    net_deviation=_money(actual_net - planned_net),
                    deviation=_money(deviation),
                    is_complete=complete,
                )
            )

        return SnapshotDetail(
            id=snapshot.id,
            label=snapshot.label,
            scenario=snapshot.scenario,
            as_of=snapshot.as_of,
            currency=snapshot.currency,
            start_balance=_money(Decimal(str(snapshot.start_balance))),
            created_at=snapshot.created_at,
            month_count=len(stored),
            elapsed_months=elapsed,
            latest_deviation=(
                _money(latest_deviation) if latest_deviation is not None else None
            ),
            months=months if with_months else [],
            mean_absolute_deviation=(
                _money(sum(deviations, _ZERO) / Decimal(len(deviations)))
                if deviations
                else None
            ),
        )

    async def _actual_net_by_period(
        self,
        mandant_id: UUID,
        *,
        since: str,
    ) -> dict[str, Decimal]:
        """Tatsächliche Kontobewegung je Monat ab dem Stichtag.

        `valuta_date > since` grenzt genau das ab, was der Snapshot noch vorhersagen
        musste: Der Anfangssaldo enthielt bereits alles bis einschließlich des Stichtags,
        auch mitten im Monat.
        """
        account_ids = await self._account_ids(mandant_id)
        if not account_ids:
            return {}

        rows = (
            await self._session.exec(
                select(
                    func.substr(JournalLine.valuta_date, 1, 7).label("period"),
                    func.sum(JournalLine.amount),
                )
                .where(
                    col(JournalLine.account_id).in_(account_ids),
                    JournalLine.currency == BASE_CURRENCY,
                    JournalLine.valuta_date > since,
                )
                .group_by("period")
            )
        ).all()
        return {str(period): Decimal(str(amount or 0)) for period, amount in rows}

    # ─── Laden ───────────────────────────────────────────────────────────────

    async def _account_ids(self, mandant_id: UUID) -> set[UUID]:
        result = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        return set(result.all())

    async def _load_forecastable_services(
        self, mandant_id: UUID
    ) -> dict[UUID, Service]:
        rows = (
            await self._session.exec(
                select(Service)
                .join(Partner, Partner.id == Service.partner_id)  # type: ignore[arg-type]
                .where(Partner.mandant_id == mandant_id)
            )
        ).all()
        return {
            service.id: service
            for service in rows
            if section_for_service(service) is not None
        }

    async def _load_monthly_series(
        self,
        mandant_id: UUID,
        service_ids: set[UUID],
    ) -> dict[UUID, dict[int, Decimal]]:
        account_ids = await self._account_ids(mandant_id)
        if not account_ids or not service_ids:
            return {}

        rows = (
            await self._session.exec(
                select(
                    JournalLineSplit.service_id,
                    func.substr(JournalLine.valuta_date, 1, 7).label("period"),
                    func.sum(JournalLineSplit.amount),
                )
                .join(JournalLine, JournalLine.id == JournalLineSplit.journal_line_id)  # type: ignore[arg-type]
                .where(
                    col(JournalLine.account_id).in_(account_ids),
                    JournalLine.currency == BASE_CURRENCY,
                    col(JournalLineSplit.service_id).in_(service_ids),
                )
                .group_by(col(JournalLineSplit.service_id), "period")
            )
        ).all()

        series: dict[UUID, dict[int, Decimal]] = {}
        for service_id, period, amount in rows:
            index = _period_to_index(str(period))
            if index is None:
                continue
            series.setdefault(service_id, {})[index] = Decimal(str(amount or 0))
        return series


#: Reihenfolge in der Liste: Wirksames zuerst, Verbrauchtes danach, Abgelaufenes zuletzt.
_PLANNED_SORT_RANK: dict[PlannedItemStatus, int] = {
    PlannedItemStatus.active: 0,
    PlannedItemStatus.partly_used: 0,
    PlannedItemStatus.used: 1,
    PlannedItemStatus.expired: 2,
}


def _period_to_index(period: str) -> int | None:
    try:
        year, month = period.split("-")
        return month_index(int(year), int(month))
    except (AttributeError, ValueError):
        return None
