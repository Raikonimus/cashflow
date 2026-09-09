"""Von der erkannten zur wirksamen Regel.

Der Profiler liefert einen Vorschlag. Darüber liegen drei Schichten, die der Nutzer
kontrolliert: die Übersteuerung je Leistung (`auto`/`manual`/`off`), die Modifikatoren
(prozentuale Anpassung, Zahlungsverzug) und das Szenario.

Reihenfolge der Anwendung — sie ist bewusst so gewählt:

    1. Regel bestimmen (Profilervorschlag oder händisch gesetzt)
    2. Zahlungsverzug: der Wert eines früheren Monats wird nach hinten geschoben
    3. Prozentuale Anpassung
    4. Szenario-Bandbreite — im Rückvergleich gemessen, sonst nach Confidence geschätzt
    5. Planposten schlägt alles: ein bekannter Betrag wird nicht geschätzt und
       nicht mit einer Bandbreite versehen

Planposten stehen deshalb ganz am Ende und ersetzen das Ergebnis, statt es zu verändern.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.forecast.models import ForecastMode, ServiceForecastRule
from app.forecast.profiler import (
    Confidence,
    ForecastProfile,
    ForecastRule,
    RuleType,
    month_index,
    seasonal_monthly_amounts,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


class Scenario(StrEnum):
    expected = "expected"
    #: Pessimistisch: weniger Einnahmen, mehr Ausgaben.
    low = "low"
    #: Optimistisch: mehr Einnahmen, weniger Ausgaben.
    high = "high"


#: Geschätzte Bandbreite je Confidence — Rückfallebene, wenn der Rückvergleich mangels
#: Historie nicht laufen konnte oder von Hand eine andere Regel gesetzt wurde.
SCENARIO_SPREAD: dict[Confidence, Decimal] = {
    Confidence.high: Decimal("0.10"),
    Confidence.medium: Decimal("0.25"),
    Confidence.low: Decimal("0.50"),
}


@dataclass(frozen=True)
class EffectiveRule:
    """Die tatsächlich angewandte Regel samt Herkunft — für Anzeige und Rechnung."""

    rule: ForecastRule
    mode: ForecastMode
    adjustment_pct: Decimal
    shift_months: int
    #: Im Rückvergleich gemessene Bandbreite. Fehlt sie, greift die Tabelle nach
    #: Confidence.
    spread: Decimal | None = None

    @property
    def is_active(self) -> bool:
        return self.rule.rule_type is not RuleType.none

    @property
    def spread_used(self) -> Decimal:
        """Die tatsächlich geltende Bandbreite — gemessen, sonst nach Confidence geschätzt."""
        if self.spread is not None:
            return self.spread
        return SCENARIO_SPREAD.get(self.rule.confidence, Decimal("0.25"))

    @property
    def reason(self) -> str:
        parts = [self.rule.reason]
        if self.adjustment_pct != _ZERO:
            parts.append(f"Anpassung {self.adjustment_pct:+.2f} %")
        if self.shift_months:
            parts.append(f"Zahlungsverzug {self.shift_months} Monat(e)")
        if self.mode is ForecastMode.manual:
            parts.append("händisch gesetzt")
        if self.spread is not None:
            parts.append(f"Bandbreite gemessen ±{self.spread * _HUNDRED:.0f} %")
        return " · ".join(parts)


def scenario_shift(
    confidence: Confidence,
    scenario: Scenario,
    measured: Decimal | None = None,
) -> Decimal:
    """Signierter Anteil, um den der Wert verschoben wird — bezogen auf seinen Betrag.

    Bewusst additiv statt multiplikativ: Ein Faktor 0,9 würde eine Ausgabe von -1.000
    auf -900 verkleinern und damit das pessimistische Szenario in sein Gegenteil
    verkehren. `low` senkt den Saldo immer, `high` hebt ihn immer — unabhängig vom
    Vorzeichen des Betrags.

    `measured` ist der im Rückvergleich gemessene relative Fehler. Er geht der Tabelle
    nach Confidence vor: Eine Messung schlägt eine Schätzung.
    """
    if scenario is Scenario.expected:
        return _ZERO
    spread = (
        measured
        if measured is not None
        else SCENARIO_SPREAD.get(confidence, Decimal("0.25"))
    )
    return -spread if scenario is Scenario.low else spread


def _params(override: ServiceForecastRule | None) -> dict[str, Any]:
    raw = override.params if override is not None else None
    return raw if isinstance(raw, dict) else {}


def _decimal(value: Any, fallback: Decimal = _ZERO) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return fallback


def _manual_rule(
    override: ServiceForecastRule,
    history: dict[int, Decimal],
    window_end: int,
    valid_from: date | None,
    valid_to: date | None,
) -> ForecastRule:
    params = _params(override)
    bounds = {
        "valid_from_index": (
            month_index(valid_from.year, valid_from.month) if valid_from else None
        ),
        "valid_to_index": (
            month_index(valid_to.year, valid_to.month) if valid_to else None
        ),
    }
    try:
        rule_type = RuleType(override.rule_type or RuleType.none.value)
    except ValueError:
        return ForecastRule(rule_type=RuleType.none, reason="Unbekannter Regeltyp")

    if rule_type is RuleType.fixed_recurring:
        interval = max(1, int(params.get("interval_months") or 1))
        anchor_month = params.get("anchor_month")
        anchor_index = None
        if interval > 1:
            month = int(anchor_month) if anchor_month else index_month_of(window_end)
            anchor_index = _anchor_from_month(window_end, month, interval)
        special = {
            int(month): _decimal(factor, Decimal("1"))
            for month, factor in (params.get("special_months") or {}).items()
        }
        interval_label = "Monatlich" if interval == 1 else f"Alle {interval} Monate"
        return ForecastRule(
            rule_type=rule_type,
            reason=f"{interval_label}, fester Betrag",
            confidence=Confidence.high,
            amount=_decimal(params.get("amount")),
            interval_months=interval,
            anchor_index=anchor_index,
            special_months=special,
            **bounds,
        )

    if rule_type is RuleType.rolling_average:
        window = max(1, int(params.get("window_months") or 6))
        total = sum(
            (history.get(window_end - offset, _ZERO) for offset in range(window)), _ZERO
        )
        return ForecastRule(
            rule_type=rule_type,
            reason=f"Ø der letzten {window} Monate",
            confidence=Confidence.medium,
            amount=total / Decimal(window),
            **bounds,
        )

    if rule_type is RuleType.same_period_last_year:
        return ForecastRule(
            rule_type=rule_type,
            reason="Wert des gleichen Monats im Vorjahr",
            confidence=Confidence.medium,
            **bounds,
        )

    if rule_type is RuleType.seasonal_profile:
        return ForecastRule(
            rule_type=rule_type,
            reason="Saisonprofil aus den letzten zwei Jahren",
            confidence=Confidence.low,
            monthly_amounts=seasonal_monthly_amounts(history, window_end),
            **bounds,
        )

    if rule_type is RuleType.manual_plan:
        return ForecastRule(
            rule_type=rule_type,
            reason="Nur händische Planposten",
            confidence=Confidence.high,
            **bounds,
        )

    return ForecastRule(
        rule_type=RuleType.none, reason="Keine Prognose (händisch gesetzt)"
    )


def index_month_of(index: int) -> int:
    return index % 12 + 1


def _anchor_from_month(window_end: int, calendar_month: int, interval: int) -> int:
    """Jüngster Monatsindex bis `window_end`, der auf den gewünschten Kalendermonat fällt."""
    candidate = window_end
    for _ in range(12):
        if index_month_of(candidate) == calendar_month:
            return candidate
        candidate -= 1
    return window_end - interval


def resolve_rule(
    profile: ForecastProfile,
    override: ServiceForecastRule | None,
    *,
    history: dict[int, Decimal],
    window_end: int,
    valid_from: date | None = None,
    valid_to: date | None = None,
    measured_spread: Decimal | None = None,
) -> EffectiveRule:
    """Verbindet Profilervorschlag und Übersteuerung zur wirksamen Regel.

    `measured_spread` stammt aus dem Rückvergleich und beschreibt den Fehler der
    *automatisch* gewählten Regel. Sobald von Hand eine andere Regel gesetzt ist, passt
    die Messung nicht mehr dazu und wird verworfen — dann greift wieder die Tabelle nach
    Confidence.
    """
    if override is None:
        return EffectiveRule(
            rule=profile.rule,
            mode=ForecastMode.auto,
            adjustment_pct=_ZERO,
            shift_months=0,
            spread=measured_spread,
        )

    try:
        mode = ForecastMode(override.mode)
    except ValueError:
        mode = ForecastMode.auto

    if mode is ForecastMode.off:
        rule = ForecastRule(rule_type=RuleType.none, reason="Prognose abgeschaltet")
    elif mode is ForecastMode.manual:
        rule = _manual_rule(override, history, window_end, valid_from, valid_to)
    else:
        rule = profile.rule

    return EffectiveRule(
        rule=rule,
        mode=mode,
        adjustment_pct=_decimal(override.adjustment_pct),
        shift_months=max(0, int(override.shift_months or 0)),
        spread=measured_spread if mode is ForecastMode.auto else None,
    )


def projected_value(
    effective: EffectiveRule,
    index: int,
    *,
    history: dict[int, Decimal],
    scenario: Scenario = Scenario.expected,
) -> Decimal:
    """Prognosewert eines Monats nach Verzug, Anpassung und Szenario."""
    base = effective.rule.value_for(index - effective.shift_months, history)
    if base == _ZERO:
        return _ZERO
    if effective.adjustment_pct != _ZERO:
        base = base * (Decimal("1") + effective.adjustment_pct / _HUNDRED)
    shift = scenario_shift(effective.rule.confidence, scenario, effective.spread)
    return base + shift * abs(base) if shift != _ZERO else base
