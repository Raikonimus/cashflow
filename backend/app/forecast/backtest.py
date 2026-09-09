"""Rückvergleich: welche Regel hätte die jüngste Vergangenheit am besten getroffen.

Bis Phase 2 wählte der Profiler die Regel nach festen Schwellwerten — plausibel, aber
geraten. Der Rückvergleich hält die letzten Monate zurück, rechnet jeden Kandidaten
ausschließlich auf den Daten davor und misst, wie weit er danebenlag. Der beste Kandidat
gewinnt und wird anschließend auf der *vollen* Historie neu angepasst; der gemessene
Fehler ersetzt die geschätzte Szenariobandbreite und die geschätzte Confidence.

Vier Entscheidungen, die nicht offensichtlich sind:

*   **Die Nullprognose läuft als Vergleichslinie mit, darf aber nicht gewinnen.**
    Bei unregelmäßigen Zahlungen hat „gar nichts vorhersagen" oft den kleinsten
    Monatsfehler — das verschiebt den Fehler nur aus dem Blickfeld. Eine Leistung, die
    verlässlich Geld bewegt, ist in einer Liquiditätsplanung mit einer ungenauen
    Schätzung besser abgebildet als mit einer Null. Ob eine Regel die Nullprognose
    überhaupt schlägt, wird trotzdem ausgewiesen — es ist die ehrlichste Kennzahl
    dafür, ob die Prognose dieser Leistung etwas taugt.

*   **Gemessen wird Timing *und* Niveau.** Der Monatsfehler (MAE) bestraft falsches
    Timing, der Niveaufehler die Abweichung der Summe über den Prüfzeitraum. Für den
    Kontostand zählt vor allem das Niveau, für die Matrix das Timing. Der Score ist das
    Mittel aus beiden, jeweils je Monat gerechnet.

*   **Der Kandidat wird auf der vollen Historie neu angepasst.** Der Rückvergleich
    entscheidet nur, *welches Verfahren* passt. Die Parameter — Median, Fenstermittel,
    Saisonanteile — kommen danach aus allen verfügbaren Monaten, sonst würde man die
    jüngsten Daten wegwerfen.

*   **Ein Kandidat muss den Profilervorschlag deutlich schlagen.** Bei sechs bis zwölf
    Prüfmonaten ist ein Vorsprung von zwei Prozent Rauschen. Erst ab
    `IMPROVEMENT_MARGIN` wird umgestellt.

Kein Datenbankzugriff, keine Zufallszahlen — dieselbe Historie ergibt dasselbe Ergebnis.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from app.forecast.profiler import (
    Confidence,
    ForecastProfile,
    ForecastRule,
    RuleType,
    build_profile,
    index_to_year_month,
    median,
    month_index,
    seasonal_monthly_amounts,
)

#: Kürzester und längster Prüfzeitraum. Er muss mindestens zwei erwartete Zahlungen
#: enthalten, damit ein Rhythmus überhaupt prüfbar ist — bei einer Jahreszahlung also
#: zwölf Monate. Länger als zwölf wird nicht geprüft, sonst bleibt zu wenig zum Lernen.
HOLDOUT_MIN_MONTHS = 6
HOLDOUT_MAX_MONTHS = 12

#: So viele Monate Historie müssen vor dem Prüfzeitraum liegen.
MIN_TRAINING_MONTHS = 12

#: Um so viel muss ein Kandidat besser sein, um den Profilervorschlag zu verdrängen.
IMPROVEMENT_MARGIN = Decimal("0.10")

#: Grenzen der gemessenen Bandbreite. Unten, weil auch eine perfekt getroffene
#: Vergangenheit keine Gewissheit über die Zukunft ist; oben, damit eine völlig
#: danebenliegende Regel nicht eine absurde Szenariobandbreite erzeugt.
SPREAD_MIN = Decimal("0.05")
SPREAD_MAX = Decimal("1.00")

#: Relativer Fehler, bis zu dem die Prognose als treffsicher gilt.
ACCURACY_HIGH_MAX = Decimal("0.10")
ACCURACY_MEDIUM_MAX = Decimal("0.30")

#: Wie stark die Prognosefehler verschiedener Leistungen zusammenhängen — damit
#: lassen sich Einzelfehler zu einer Bandbreite für den Kontostand zusammenfassen.
#:
#: 0 hieße vollständig unabhängig: Fehler heben sich weitgehend auf, das Band wächst
#: nur mit der Wurzel. 1 hieße gleichgerichtet: jede Regel irrt zugleich in dieselbe
#: Richtung, die Fehler addieren sich.
#:
#: Beides ist falsch. Unabhängigkeit unterschätzt gefährlich, weil die großen
#: Erlöszeilen eines kleinen Unternehmens an denselben Treibern hängen — Markt,
#: Pipeline, ein Großkunde. Am Beispielmandanten wäre ein unabhängig gerechnetes Band
#: in allen sechs rückwirkend geprüften Monaten zu eng gewesen; nötig gewesen wäre eine
#: Korrelation, die über den Horizont auf 0,4 anwächst. 0,5 deckt das mit Reserve ab
#: und sagt in einem Satz, was gemeint ist: Die Hälfte des Fehlers ist gemeinsam, die
#: Hälfte eigen.
ERROR_CORRELATION = Decimal("0.5")


def combined_uncertainty(deviations: list[Decimal]) -> Decimal:
    """Fasst Einzelabweichungen zu einer Bandbreite zusammen.

    Formel für gleichkorrelierte Terme:
    ``Var = (1−ρ)·Σσᵢ² + ρ·(Σσᵢ)²``. Bei ρ=0 ist das die Wurzel aus der Summe der
    Quadrate, bei ρ=1 die einfache Summe.
    """
    if not deviations:
        return _ZERO
    squares = sum((value * value for value in deviations), _ZERO)
    total = sum(deviations, _ZERO)
    variance = (_ONE - ERROR_CORRELATION) * squares + ERROR_CORRELATION * total * total
    return variance.sqrt() if variance > _ZERO else _ZERO


_ZERO = Decimal("0")
_ONE = Decimal("1")

#: Fenster der geprüften gleitenden Mittelwerte.
ROLLING_WINDOWS = (3, 6, 12)


@dataclass(frozen=True)
class Candidate:
    """Ein Verfahren, nicht eine fertige Regel — es wird zweimal angewandt.

    Einmal auf den Trainingsdaten (zum Messen), einmal auf der vollen Historie
    (für die tatsächliche Prognose).
    """

    key: str
    label: str
    build: Callable[[dict[int, Decimal], int], ForecastRule]
    is_baseline: bool = False


@dataclass(frozen=True)
class CandidateScore:
    key: str
    label: str
    #: Mittlerer absoluter Monatsfehler.
    mae: Decimal
    #: Vorzeichenbehaftete Abweichung der Summe: positiv = zu hoch prognostiziert.
    level_error: Decimal
    #: Was über den Sieger entscheidet: Mittel aus Monats- und Niveaufehler je Monat.
    score: Decimal
    is_baseline: bool = False


@dataclass(frozen=True)
class BacktestReport:
    """Ergebnis des Rückvergleichs für eine Leistung."""

    ran: bool
    reason: str
    holdout_months: int = 0
    train_end_index: int | None = None
    #: Σ|Ist| im Prüfzeitraum — Bezugsgröße für den relativen Fehler.
    actual_volume: Decimal = _ZERO
    scores: tuple[CandidateScore, ...] = ()
    winner: CandidateScore | None = None
    baseline: CandidateScore | None = None
    #: Der Sieger, neu angepasst auf der vollen Historie. `None`, wenn nichts lief.
    fitted_rule: ForecastRule | None = None
    #: Ob der Sieger ein anderes Verfahren ist als der Profilervorschlag.
    replaced_detected: bool = False
    #: Im Prüfzeitraum lag keine Buchung — die Leistung wird als beendet gewertet.
    service_stopped: bool = False

    @property
    def relative_error(self) -> Decimal | None:
        """Monatsfehler im Verhältnis zum monatlichen Ist-Volumen."""
        if self.winner is None or not self.holdout_months:
            return None
        if self.actual_volume <= _ZERO:
            return None
        volume_per_month = self.actual_volume / Decimal(self.holdout_months)
        return self.winner.score / volume_per_month

    @property
    def beats_baseline(self) -> bool:
        """Ob die Regel besser trifft als "gar nichts vorhersagen"."""
        if self.winner is None or self.baseline is None:
            return False
        return self.winner.score < self.baseline.score

    @property
    def spread(self) -> Decimal | None:
        """Gemessene Bandbreite für die Szenarien — der relative Fehler, gedeckelt."""
        relative = self.relative_error
        if relative is None:
            return None
        return min(max(relative, SPREAD_MIN), SPREAD_MAX)

    @property
    def confidence(self) -> Confidence | None:
        """Confidence aus der Messung statt aus Schwellwerten."""
        relative = self.relative_error
        if relative is None:
            return None
        if relative <= ACCURACY_HIGH_MAX:
            return Confidence.high
        if relative <= ACCURACY_MEDIUM_MAX:
            return Confidence.medium
        return Confidence.low


def _month_label(index: int) -> str:
    year, month = index_to_year_month(index)
    return f"{month:02d}/{year}"


def holdout_months_for(rule: ForecastRule) -> int:
    """Prüfzeitraum: mindestens zwei erwartete Zahlungen, höchstens ein Jahr."""
    interval = rule.interval_months if rule.rule_type is RuleType.fixed_recurring else 1
    return min(HOLDOUT_MAX_MONTHS, max(HOLDOUT_MIN_MONTHS, 2 * max(1, interval)))


def _bounds(valid_from: date | None, valid_to: date | None) -> dict[str, int | None]:
    return {
        "valid_from_index": (
            month_index(valid_from.year, valid_from.month) if valid_from else None
        ),
        "valid_to_index": (
            month_index(valid_to.year, valid_to.month) if valid_to else None
        ),
    }


def _candidates(
    *,
    valid_from: date | None,
    valid_to: date | None,
) -> list[Candidate]:
    """Alle Verfahren, die für eine beliebige Monatsreihe in Frage kommen."""
    bounds = _bounds(valid_from, valid_to)

    def detected(points: dict[int, Decimal], window_end: int) -> ForecastRule:
        return build_profile(
            points, window_end=window_end, valid_from=valid_from, valid_to=valid_to
        ).rule

    def fixed_monthly(points: dict[int, Decimal], window_end: int) -> ForecastRule:
        active = [amount for amount in points.values() if amount != _ZERO]
        return ForecastRule(
            rule_type=RuleType.fixed_recurring,
            reason="Fester Monatsbetrag (Median der Buchungen)",
            confidence=Confidence.medium,
            amount=median(active),
            interval_months=1,
            **bounds,
        )

    def rolling(window: int) -> Callable[[dict[int, Decimal], int], ForecastRule]:
        def build(points: dict[int, Decimal], window_end: int) -> ForecastRule:
            total = sum(
                (points.get(window_end - offset, _ZERO) for offset in range(window)),
                _ZERO,
            )
            return ForecastRule(
                rule_type=RuleType.rolling_average,
                reason=f"Ø der letzten {window} Monate",
                confidence=Confidence.medium,
                amount=total / Decimal(window),
                **bounds,
            )

        return build

    def last_year(points: dict[int, Decimal], window_end: int) -> ForecastRule:
        return ForecastRule(
            rule_type=RuleType.same_period_last_year,
            reason="Wert des gleichen Monats im Vorjahr",
            confidence=Confidence.medium,
            **bounds,
        )

    def seasonal(points: dict[int, Decimal], window_end: int) -> ForecastRule:
        return ForecastRule(
            rule_type=RuleType.seasonal_profile,
            reason="Saisonprofil aus den letzten zwei Jahren",
            confidence=Confidence.low,
            monthly_amounts=seasonal_monthly_amounts(points, window_end),
            **bounds,
        )

    def nothing(points: dict[int, Decimal], window_end: int) -> ForecastRule:
        return ForecastRule(rule_type=RuleType.none, reason="Keine Prognose")

    candidates = [
        Candidate("detected", "Erkanntes Muster", detected),
        Candidate("fixed_monthly", "Fester Monatsbetrag", fixed_monthly),
        *(
            Candidate(
                f"rolling_average:{window}", f"Ø {window} Monate", rolling(window)
            )
            for window in ROLLING_WINDOWS
        ),
        Candidate("same_period_last_year", "Vorjahresmonat", last_year),
        Candidate("seasonal_profile", "Saisonprofil", seasonal),
        Candidate("none", "Nullprognose (Vergleich)", nothing, is_baseline=True),
    ]
    return candidates


def _score(
    rule: ForecastRule,
    train: dict[int, Decimal],
    series: dict[int, Decimal],
    holdout: range,
) -> tuple[Decimal, Decimal]:
    """(Monatsfehler, vorzeichenbehafteter Niveaufehler) über den Prüfzeitraum.

    Die Regel sieht ausschließlich `train` — auch `same_period_last_year` schlägt dort
    nach, nie in den zurückgehaltenen Monaten.
    """
    absolute_total = _ZERO
    signed_total = _ZERO
    for index in holdout:
        predicted = rule.value_for(index, train)
        actual = series.get(index, _ZERO)
        deviation = predicted - actual
        absolute_total += abs(deviation)
        signed_total += deviation
    count = Decimal(len(holdout))
    return absolute_total / count, signed_total


def run_backtest(
    points: dict[int, Decimal],
    *,
    window_end: int,
    profile: ForecastProfile,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> BacktestReport:
    """Misst alle Kandidaten am zurückgehaltenen Prüfzeitraum und wählt den besten.

    `points` ist dieselbe Monatsreihe, aus der `profile` entstanden ist; `window_end`
    derselbe letzte Ist-Monat.
    """
    if profile.rule.rule_type is RuleType.none:
        # Der Profiler hat bewusst abgelehnt — zu wenig Historie oder Leistung beendet.
        # Diese Sperren sind eine Ehrlichkeitsgrenze und werden nicht überstimmt.
        return BacktestReport(
            ran=False, reason="Kein Muster erkannt — nichts zu vergleichen"
        )

    if profile.first_index is None:
        return BacktestReport(
            ran=False, reason="Keine Buchungen im Beobachtungszeitraum"
        )

    holdout_months = holdout_months_for(profile.rule)
    train_end = window_end - holdout_months
    if profile.first_index > train_end - MIN_TRAINING_MONTHS + 1:
        return BacktestReport(
            ran=False,
            reason=(
                f"Historie reicht nicht: {MIN_TRAINING_MONTHS} Monate vor dem "
                f"{holdout_months}-Monats-Prüfzeitraum nötig"
            ),
            holdout_months=holdout_months,
        )

    train = {index: amount for index, amount in points.items() if index <= train_end}
    holdout = range(train_end + 1, window_end + 1)
    actual_volume = sum((abs(points.get(index, _ZERO)) for index in holdout), _ZERO)

    if actual_volume == _ZERO:
        # Der Prüfzeitraum ist so bemessen, dass mindestens zwei erwartete Zahlungen
        # hineinfallen. Ist er komplett leer, fließt hier nichts mehr — das ist gemessen
        # und nicht geschätzt, und deshalb strenger als die Schwellwertregel des
        # Profilers, die eine ausgelaufene Leistung noch monatelang weiterprojiziert.
        return BacktestReport(
            ran=True,
            reason=(
                f"{_month_label(train_end + 1)}–{_month_label(window_end)} ohne jede "
                "Buchung — Leistung gilt als beendet"
            ),
            holdout_months=holdout_months,
            train_end_index=train_end,
            service_stopped=True,
            fitted_rule=ForecastRule(
                rule_type=RuleType.none,
                reason=(
                    f"Seit {holdout_months} Monaten keine Buchung mehr — "
                    "im Rückvergleich als beendet erkannt"
                ),
            ),
        )

    scores: list[CandidateScore] = []
    by_key: dict[str, Candidate] = {}
    for candidate in _candidates(valid_from=valid_from, valid_to=valid_to):
        rule = candidate.build(train, train_end)
        if rule.rule_type is RuleType.none and not candidate.is_baseline:
            # Auf den kürzeren Trainingsdaten kommt dieses Verfahren nicht zustande.
            continue
        mae, level_error = _score(rule, train, points, holdout)
        by_key[candidate.key] = candidate
        scores.append(
            CandidateScore(
                key=candidate.key,
                label=candidate.label,
                mae=mae,
                level_error=level_error,
                score=(mae + abs(level_error) / Decimal(holdout_months)) / Decimal("2"),
                is_baseline=candidate.is_baseline,
            )
        )

    scores.sort(key=lambda entry: entry.score)
    baseline = next((entry for entry in scores if entry.is_baseline), None)
    eligible = [entry for entry in scores if not entry.is_baseline]
    if not eligible:
        return BacktestReport(
            ran=False,
            reason="Kein Kandidat auf der kürzeren Historie berechenbar",
            holdout_months=holdout_months,
        )

    detected = next((entry for entry in eligible if entry.key == "detected"), None)
    winner = eligible[0]
    if detected is not None and winner.key != "detected":
        # Nur ein deutlicher Vorsprung rechtfertigt es, den Profiler zu überstimmen.
        if winner.score > detected.score * (_ONE - IMPROVEMENT_MARGIN):
            winner = detected

    fitted = by_key[winner.key].build(points, window_end)
    report = BacktestReport(
        ran=True,
        reason=f"Rückvergleich über {holdout_months} Monate",
        holdout_months=holdout_months,
        train_end_index=train_end,
        actual_volume=actual_volume,
        scores=tuple(scores),
        winner=winner,
        baseline=baseline,
        fitted_rule=fitted,
        replaced_detected=winner.key != "detected",
    )

    measured = report.confidence
    fitted_reason = fitted.reason
    if report.replaced_detected:
        fitted_reason = f"{fitted_reason} — im Rückvergleich beste Regel"
    report = replace(
        report,
        fitted_rule=replace(
            fitted,
            reason=fitted_reason,
            confidence=measured if measured is not None else fitted.confidence,
        ),
    )
    return report


def applied_profile(
    profile: ForecastProfile,
    report: BacktestReport,
) -> ForecastProfile:
    """Das Profil, wie es nach dem Rückvergleich tatsächlich gilt."""
    if not report.ran or report.fitted_rule is None:
        return profile
    return replace(profile, rule=report.fitted_rule)
