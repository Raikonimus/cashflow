"""Mustererkennung und Projektion je Leistung — rein arithmetisch, ohne Datenbankzugriff.

Der Profiler bekommt eine Monatsreihe (Bruttosummen nach Valutadatum) und leitet daraus
eine Regel ab, mit der künftige Monate berechnet werden. Alles ist deterministisch und
erklärbar: Zu jeder Regel gehört ein `reason`, der in der Oberfläche angezeigt werden kann.

Vorzeichen werden durchgereicht — Ausgaben sind negativ, Einnahmen positiv.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

# Länge des Beobachtungsfensters in Monaten.
HISTORY_WINDOW_MONTHS = 36

# Ab welchem Anteil belegter Monate ein Rhythmus als "monatlich" gilt.
MONTHLY_COVERAGE_MIN = Decimal("0.7")

# Streuung (MAD/|Median|), bis zu der ein Betrag als konstant bzw. stabil gilt.
DISPERSION_FIXED_MAX = Decimal("0.05")
DISPERSION_STABLE_MAX = Decimal("0.25")

# Ab diesem Vielfachen des Jahresmedians gilt ein Kalendermonat als Sondermonat
# (13./14. Gehalt, Boni, Jahresprämien).
SPECIAL_MONTH_FACTOR_MIN = Decimal("1.5")
SPECIAL_MONTH_MIN_OBSERVATIONS = 2

# Mindestanzahl an Vorkommen je Regeltyp. Zwei Jahreszahlungen im selben Kalendermonat
# sind ein Muster (sie spannen zwölf Monate); zwei Quartalszahlungen spannen nur vier
# und sind noch kein Beleg — dort braucht es drei.
MIN_OCCURRENCES_MONTHLY = 3
MIN_OCCURRENCES_ANNUAL = 2
MIN_OCCURRENCES_QUARTERLY = 3

# Fenstergrößen für gleitende Mittelwerte.
ROLLING_WINDOW_VOLATILE = 6
ROLLING_WINDOW_IRREGULAR = 12

_ZERO = Decimal("0")


class Cadence(StrEnum):
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"
    irregular = "irregular"
    none = "none"


class RuleType(StrEnum):
    fixed_recurring = "fixed_recurring"
    rolling_average = "rolling_average"
    #: Wert des gleichen Monats im Vorjahr — für saisonales Geschäft.
    same_period_last_year = "same_period_last_year"
    #: Kalendermonats-Durchschnitt aus den Vorjahren.
    seasonal_profile = "seasonal_profile"
    #: Werte kommen ausschließlich aus händischen Planposten.
    manual_plan = "manual_plan"
    none = "none"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


def month_index(year: int, month: int) -> int:
    """Fortlaufender Monatsindex, damit Abstände ohne Kalenderlogik rechenbar sind."""
    return year * 12 + (month - 1)


def index_to_year_month(index: int) -> tuple[int, int]:
    return index // 12, index % 12 + 1


@dataclass(frozen=True)
class ForecastRule:
    rule_type: RuleType
    reason: str
    confidence: Confidence = Confidence.low
    amount: Decimal = _ZERO
    interval_months: int = 1
    # Referenzmonat für Intervalle > 1: an ihm hängt das Raster künftiger Zahlungen.
    anchor_index: int | None = None
    special_months: dict[int, Decimal] = field(default_factory=dict)
    # Gültigkeitsgrenzen aus den Stammdaten der Leistung — außerhalb wird nichts projiziert.
    valid_from_index: int | None = None
    valid_to_index: int | None = None
    #: Kalendermonat → Betrag, für `seasonal_profile`.
    monthly_amounts: dict[int, Decimal] = field(default_factory=dict)

    def value_for(
        self, index: int, history: dict[int, Decimal] | None = None
    ) -> Decimal:
        """Prognostizierter Bruttobetrag für einen Monatsindex.

        `history` wird nur von `same_period_last_year` gebraucht.
        """
        if self.rule_type in (RuleType.none, RuleType.manual_plan):
            return _ZERO
        if self.valid_from_index is not None and index < self.valid_from_index:
            return _ZERO
        if self.valid_to_index is not None and index > self.valid_to_index:
            return _ZERO
        if self.rule_type is RuleType.rolling_average:
            return self.amount
        if self.rule_type is RuleType.seasonal_profile:
            return self.monthly_amounts.get(index_to_year_month(index)[1], _ZERO)
        if self.rule_type is RuleType.same_period_last_year:
            return _lookup_last_year(history or {}, index)
        if self.interval_months > 1:
            if self.anchor_index is None:
                return _ZERO
            if (index - self.anchor_index) % self.interval_months != 0:
                return _ZERO
            return self.amount
        factor = self.special_months.get(index_to_year_month(index)[1], Decimal("1"))
        return self.amount * factor


@dataclass(frozen=True)
class ForecastProfile:
    cadence: Cadence
    occurrence_count: int
    median_amount: Decimal
    dispersion: Decimal | None
    first_index: int | None
    last_index: int | None
    special_months: dict[int, Decimal]
    rule: ForecastRule


def _lookup_last_year(history: dict[int, Decimal], index: int) -> Decimal:
    """Wert desselben Kalendermonats im Vorjahr.

    Liegt auch das Vorjahr schon im Prognosezeitraum, wird schrittweise weiter
    zurückgegangen, bis ein echter Ist-Wert gefunden ist.
    """
    probe = index - 12
    for _ in range(4):
        if probe in history:
            return history[probe]
        probe -= 12
    return _ZERO


def seasonal_monthly_amounts(
    points: dict[int, Decimal],
    window_end: int,
    years: int = 2,
) -> dict[int, Decimal]:
    """Kalendermonats-Durchschnitt der letzten `years` Jahre — das Saisonprofil."""
    buckets: dict[int, list[Decimal]] = {month: [] for month in range(1, 13)}
    for offset in range(years * 12):
        index = window_end - offset
        buckets[index_to_year_month(index)[1]].append(points.get(index, _ZERO))
    return {
        month: (sum(values, _ZERO) / Decimal(len(values))) if values else _ZERO
        for month, values in buckets.items()
    }


def median(values: list[Decimal]) -> Decimal:
    if not values:
        return _ZERO
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _median_absolute_deviation(values: list[Decimal], center: Decimal) -> Decimal:
    if not values:
        return _ZERO
    return median([abs(value - center) for value in values])


def _detect_cadence(gaps: list[int]) -> tuple[Cadence, int]:
    """Rhythmus aus den Abständen zwischen belegten Monaten. Rückgabe: (Rhythmus, Intervall)."""
    if not gaps:
        return Cadence.none, 0

    median_gap = int(median([Decimal(gap) for gap in gaps]))
    # Unregelmäßig, sobald die Abstände stark schwanken.
    deviation = _median_absolute_deviation(
        [Decimal(gap) for gap in gaps], Decimal(median_gap)
    )
    if deviation > Decimal("1"):
        return Cadence.irregular, 0

    if median_gap == 1:
        return Cadence.monthly, 1
    if 2 <= median_gap <= 4:
        return Cadence.quarterly, median_gap
    if 5 <= median_gap <= 7:
        return Cadence.quarterly, median_gap  # halbjährlich läuft über dasselbe Raster
    if 11 <= median_gap <= 13:
        return Cadence.annual, 12
    return Cadence.irregular, 0


def _detect_special_months(
    points: dict[int, Decimal],
    baseline: Decimal,
) -> dict[int, Decimal]:
    """Kalendermonate, die wiederholt deutlich über dem Median liegen (13./14. Gehalt)."""
    if baseline == _ZERO:
        return {}

    by_calendar_month: dict[int, list[Decimal]] = {}
    for index, amount in points.items():
        by_calendar_month.setdefault(index_to_year_month(index)[1], []).append(amount)

    special: dict[int, Decimal] = {}
    for calendar_month, amounts in by_calendar_month.items():
        if len(amounts) < SPECIAL_MONTH_MIN_OBSERVATIONS:
            continue
        factors = [amount / baseline for amount in amounts]
        # Jede einzelne Beobachtung muss erhöht sein. Sonst würde bei genau zwei
        # Beobachtungen eine einmalige Nachzahlung den Median hochziehen und den
        # Monat dauerhaft als Sondermonat festschreiben.
        if min(factors) < SPECIAL_MONTH_FACTOR_MIN:
            continue
        special[calendar_month] = median(factors)
    return special


def _rolling_average(
    points: dict[int, Decimal], window_end: int, window: int
) -> Decimal:
    """Mittel über die letzten `window` Kalendermonate — Nullmonate zählen mit."""
    total = _ZERO
    for offset in range(window):
        total += points.get(window_end - offset, _ZERO)
    return total / Decimal(window)


def _month_label(index: int) -> str:
    year, month = index_to_year_month(index)
    return f"{month:02d}/{year}"


def build_profile(
    points: dict[int, Decimal],
    *,
    window_end: int,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> ForecastProfile:
    """Leitet Muster und Prognoseregel aus der Monatsreihe einer Leistung ab.

    `points` enthält nur belegte Monate (Index → Bruttosumme). `window_end` ist der
    letzte vollständige Monat; alles danach ist Prognosezeitraum.
    """
    window_start = window_end - HISTORY_WINDOW_MONTHS + 1
    active = {
        index: amount
        for index, amount in points.items()
        if window_start <= index <= window_end and amount != _ZERO
    }

    if valid_to is not None and month_index(valid_to.year, valid_to.month) < window_end:
        return _empty_profile(
            active,
            f"Leistung endete {valid_to.isoformat()} — keine Prognose",
        )

    if not active:
        return _empty_profile(
            active, "Keine Buchungen im Beobachtungszeitraum — keine Prognose"
        )

    indices = sorted(active)
    first_index, last_index = indices[0], indices[-1]
    gaps = [later - earlier for earlier, later in zip(indices, indices[1:])]
    cadence, interval = _detect_cadence(gaps)

    amounts = [active[index] for index in indices]
    median_amount = median(amounts)
    dispersion = (
        _median_absolute_deviation(amounts, median_amount) / abs(median_amount)
        if median_amount != _ZERO
        else None
    )

    span = last_index - first_index + 1
    coverage = Decimal(len(indices)) / Decimal(span) if span > 0 else _ZERO
    if cadence is Cadence.monthly and coverage < MONTHLY_COVERAGE_MIN:
        cadence = Cadence.irregular
        interval = 0

    special_months = (
        _detect_special_months(active, median_amount)
        if cadence is Cadence.monthly
        else {}
    )

    # Karteileichen: seit mehr als zwei erwarteten Perioden nichts mehr gebucht.
    # Untergrenze 3 Monate, damit eine einzelne ausgefallene Zahlung eine monatliche
    # Leistung nicht sofort für beendet erklärt.
    expected_interval = interval if interval > 0 else ROLLING_WINDOW_IRREGULAR
    if last_index < window_end - max(2 * expected_interval, 3):
        return _empty_profile(
            active,
            f"Seit {_month_label(last_index)} keine Buchung — Leistung gilt als beendet",
            cadence=cadence,
            median_amount=median_amount,
            dispersion=dispersion,
        )

    rule = _select_rule(
        cadence=cadence,
        interval=interval,
        occurrence_count=len(indices),
        median_amount=median_amount,
        dispersion=dispersion,
        special_months=special_months,
        active=active,
        first_index=first_index,
        last_index=last_index,
        window_end=window_end,
        valid_from=valid_from,
        valid_to=valid_to,
    )

    return ForecastProfile(
        cadence=cadence,
        occurrence_count=len(indices),
        median_amount=median_amount,
        dispersion=dispersion,
        first_index=first_index,
        last_index=last_index,
        special_months=special_months,
        rule=rule,
    )


def _empty_profile(
    active: dict[int, Decimal],
    reason: str,
    *,
    cadence: Cadence = Cadence.none,
    median_amount: Decimal = _ZERO,
    dispersion: Decimal | None = None,
) -> ForecastProfile:
    indices = sorted(active)
    return ForecastProfile(
        cadence=cadence,
        occurrence_count=len(indices),
        median_amount=median_amount,
        dispersion=dispersion,
        first_index=indices[0] if indices else None,
        last_index=indices[-1] if indices else None,
        special_months={},
        rule=ForecastRule(rule_type=RuleType.none, reason=reason),
    )


def _select_rule(
    *,
    cadence: Cadence,
    interval: int,
    occurrence_count: int,
    median_amount: Decimal,
    dispersion: Decimal | None,
    special_months: dict[int, Decimal],
    active: dict[int, Decimal],
    first_index: int,
    last_index: int,
    window_end: int,
    valid_from: date | None,
    valid_to: date | None = None,
) -> ForecastRule:
    history_span = window_end - first_index + 1
    bounds = {
        "valid_from_index": (
            month_index(valid_from.year, valid_from.month) if valid_from else None
        ),
        "valid_to_index": (
            month_index(valid_to.year, valid_to.month) if valid_to else None
        ),
    }

    if cadence is Cadence.monthly:
        if occurrence_count < MIN_OCCURRENCES_MONTHLY:
            return ForecastRule(
                rule_type=RuleType.none,
                reason=f"Nur {occurrence_count} Buchungen — mindestens {MIN_OCCURRENCES_MONTHLY} nötig",
            )
        if dispersion is not None and dispersion <= DISPERSION_STABLE_MAX:
            confidence = (
                Confidence.high
                if dispersion <= DISPERSION_FIXED_MAX and occurrence_count >= 6
                else Confidence.medium
            )
            extra = (
                f", Sondermonate {'/'.join(f'{month:02d}' for month in sorted(special_months))}"
                if special_months
                else ""
            )
            return ForecastRule(
                rule_type=RuleType.fixed_recurring,
                reason=f"Monatlich, stabiler Betrag (Median aus {occurrence_count} Buchungen){extra}",
                confidence=confidence,
                amount=median_amount,
                interval_months=1,
                special_months=special_months,
                **bounds,
            )
        if history_span < ROLLING_WINDOW_VOLATILE:
            return ForecastRule(
                rule_type=RuleType.none,
                reason=f"Monatlich, aber schwankend und erst {history_span} Monate Historie",
            )
        return ForecastRule(
            rule_type=RuleType.rolling_average,
            reason=f"Monatlich, aber schwankend — Ø der letzten {ROLLING_WINDOW_VOLATILE} Monate",
            confidence=Confidence.medium,
            amount=_rolling_average(active, window_end, ROLLING_WINDOW_VOLATILE),
            **bounds,
        )

    if cadence in (Cadence.quarterly, Cadence.annual):
        minimum = (
            MIN_OCCURRENCES_ANNUAL
            if cadence is Cadence.annual
            else MIN_OCCURRENCES_QUARTERLY
        )
        if occurrence_count < minimum:
            return ForecastRule(
                rule_type=RuleType.none,
                reason=f"Nur {occurrence_count} Buchungen — mindestens {minimum} nötig",
            )
        anchor_index = last_index
        if valid_from is not None:
            start = month_index(valid_from.year, valid_from.month)
            if start > anchor_index:
                anchor_index = start
        label = "Jährlich" if cadence is Cadence.annual else f"Alle {interval} Monate"
        confidence = Confidence.medium if occurrence_count >= 3 else Confidence.low
        return ForecastRule(
            rule_type=RuleType.fixed_recurring,
            reason=f"{label}, zuletzt {_month_label(last_index)} (Median aus {occurrence_count} Buchungen)",
            confidence=confidence,
            amount=median_amount,
            interval_months=interval,
            anchor_index=anchor_index,
            **bounds,
        )

    # Unregelmäßig: Der einzelne Monat ist nicht treffbar, nur die Verteilung.
    if history_span < ROLLING_WINDOW_IRREGULAR:
        return ForecastRule(
            rule_type=RuleType.none,
            reason=f"Unregelmäßig und erst {history_span} Monate Historie — mindestens {ROLLING_WINDOW_IRREGULAR} nötig",
        )
    return ForecastRule(
        rule_type=RuleType.rolling_average,
        reason=f"Unregelmäßig — Jahresdurchschnitt der letzten {ROLLING_WINDOW_IRREGULAR} Monate",
        confidence=Confidence.low,
        amount=_rolling_average(active, window_end, ROLLING_WINDOW_IRREGULAR),
        **bounds,
    )
