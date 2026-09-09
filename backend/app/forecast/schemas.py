from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.forecast.models import ForecastMode
from app.forecast.profiler import RuleType

PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"

#: Regeltypen, die sich von Hand setzen lassen.
SELECTABLE_RULE_TYPES = {
    RuleType.fixed_recurring.value,
    RuleType.rolling_average.value,
    RuleType.same_period_last_year.value,
    RuleType.seasonal_profile.value,
    RuleType.manual_plan.value,
    RuleType.none.value,
}


class ForecastPreviewMonth(BaseModel):
    period: str
    amount: str
    is_planned: bool = False


class BacktestCandidateResponse(BaseModel):
    """Ein geprüftes Verfahren mit seinem gemessenen Fehler."""

    key: str
    label: str
    #: Mittlerer absoluter Monatsfehler.
    mae: str
    #: Abweichung der Summe über den Prüfzeitraum; positiv = zu hoch prognostiziert.
    level_error: str
    score: str
    is_baseline: bool = False
    is_winner: bool = False


class BacktestResponse(BaseModel):
    ran: bool
    reason: str
    holdout_months: int = 0
    holdout_from: str | None = None
    holdout_to: str | None = None
    #: Σ|Ist| im Prüfzeitraum.
    actual_volume: str = "0.00"
    #: Monatsfehler im Verhältnis zum monatlichen Ist-Volumen, als Anteil.
    relative_error: str | None = None
    #: Gemessene Szenariobandbreite, als Anteil.
    spread: str | None = None
    #: Ob die Regel besser trifft als "gar nichts vorhersagen".
    beats_baseline: bool = False
    #: Ob der Rückvergleich den Profilervorschlag verworfen hat.
    replaced_detected: bool = False
    #: Im Prüfzeitraum lag keine Buchung — die Leistung wird als beendet gewertet.
    service_stopped: bool = False
    candidates: list[BacktestCandidateResponse] = []


class ForecastRuleResponse(BaseModel):
    service_id: UUID
    service_name: str
    partner_name: str | None = None
    mode: ForecastMode
    rule_type: str | None = None
    params: dict[str, Any] | None = None
    adjustment_pct: Decimal
    shift_months: int

    #: Was der Profiler von sich aus erkennt — bleibt sichtbar, auch wenn übersteuert wird.
    detected_cadence: str
    detected_rule_type: str
    detected_reason: str
    occurrence_count: int
    median_amount: str

    #: Was tatsächlich gerechnet wird.
    effective_rule_type: str
    effective_reason: str
    confidence: str | None = None
    preview: list[ForecastPreviewMonth] = []
    backtest: BacktestResponse | None = None

    model_config = {"from_attributes": True}


class UpdateForecastRuleRequest(BaseModel):
    mode: ForecastMode = ForecastMode.auto
    rule_type: str | None = None
    params: dict[str, Any] | None = None
    adjustment_pct: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("-100"), le=Decimal("1000")
    )
    shift_months: int = Field(default=0, ge=0, le=12)

    @model_validator(mode="after")
    def validate_manual(self) -> "UpdateForecastRuleRequest":
        if self.mode is ForecastMode.manual:
            if not self.rule_type:
                raise ValueError("rule_type is required when mode is 'manual'")
            if self.rule_type not in SELECTABLE_RULE_TYPES:
                raise ValueError(
                    f"rule_type must be one of {sorted(SELECTABLE_RULE_TYPES)}"
                )
        return self


class ForecastServiceOverviewRow(BaseModel):
    service_id: UUID
    service_name: str
    partner_id: UUID
    partner_name: str | None = None
    section: str
    mode: ForecastMode
    effective_rule_type: str
    effective_reason: str
    confidence: str | None = None
    detected_cadence: str
    occurrence_count: int
    last_booking_period: str | None = None
    #: Summe der nächsten zwölf Prognosemonate — sortierbares Maß für die Relevanz.
    next_12_months: str
    planned_item_count: int = 0
    #: Modifikatoren, damit in der Liste sichtbar wird, wo von Hand eingegriffen wurde.
    #: Ohne sie sähe eine Leistung mit +100 % Anpassung wie eine unberührte aus.
    adjustment_pct: Decimal = Decimal("0.00")
    shift_months: int = 0
    #: Ob überhaupt etwas von Hand eingestellt ist — Modus, Modifikator oder Planposten.
    #: Die Entscheidung fällt im Backend, damit Zählung und Filter nicht auseinanderlaufen.
    customised: bool = False
    #: Gemessener relativer Fehler aus dem Rückvergleich, als Anteil. None = nicht messbar.
    relative_error: str | None = None
    backtest_ran: bool = False
    beats_baseline: bool = False
    replaced_detected: bool = False
    service_stopped: bool = False


class ForecastOverviewResponse(BaseModel):
    services: list[ForecastServiceOverviewRow]
    total: int
    #: Anzahl Leistungen ohne wirksame Regel — die Lücke der Prognose.
    without_rule: int
    #: Anzahl Leistungen, an denen von Hand etwas eingestellt ist.
    customised: int = 0
    #: Leistungen, deren Regel am Rückvergleich gemessen werden konnte.
    backtested: int = 0
    #: Davon: Regel wurde wegen des Rückvergleichs gewechselt.
    replaced_by_backtest: int = 0
    #: Davon: im Prüfzeitraum keine Buchung mehr — Prognose abgeschaltet.
    stopped_by_backtest: int = 0
    #: Davon: Regel läuft weiter, trifft aber schlechter als "gar nichts vorhersagen".
    weak_forecasts: int = 0
    #: Typischer relativer Fehler über alle gemessenen Leistungen (Median).
    median_relative_error: str | None = None


# ─── Plan-Ist-Snapshots ───────────────────────────────────────────────────────


class CreateSnapshotRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    scenario: str = Field(default="expected")


class SnapshotMonthComparison(BaseModel):
    period: str
    planned_net: str
    planned_closing: str
    #: None, solange der Monat noch in der Zukunft liegt.
    actual_net: str | None = None
    actual_closing: str | None = None
    #: Ist minus Plan in diesem Monat — zeigt, welcher Monat aus dem Ruder lief.
    net_deviation: str | None = None
    #: Ist-Endsaldo minus Plan-Endsaldo, also die aufgelaufene Abweichung. Sie ist die
    #: für die Liquidität entscheidende Zahl: Ein guter Monat gleicht einen schlechten aus.
    deviation: str | None = None
    #: Ob der Monat vollständig abgelaufen ist. Der laufende zählt nur anteilig.
    is_complete: bool = False


class SnapshotSummary(BaseModel):
    id: UUID
    label: str | None = None
    scenario: str
    as_of: str
    currency: str
    start_balance: str
    created_at: datetime
    month_count: int
    #: Anzahl vollständig abgelaufener Monate — nur diese gehen in die Messung ein.
    elapsed_months: int = 0
    #: Abweichung des Endsaldos im jüngsten vollständig abgelaufenen Monat.
    latest_deviation: str | None = None


class SnapshotDetail(SnapshotSummary):
    months: list[SnapshotMonthComparison] = []
    #: Mittlere absolute Abweichung des Monatssaldos über die abgelaufenen Monate.
    mean_absolute_deviation: str | None = None


class PlannedItemStatus(StrEnum):
    """Wieviel ein Planposten noch zur Prognose beiträgt.

    Ein Posten wird nie gelöscht, wenn echte Buchungen eintreffen — er verliert nur seine
    Wirkung. Ohne diese Unterscheidung sammelt sich in der Liste ein Bestand, dem man
    nicht ansieht, was davon noch zählt.
    """

    #: Monat liegt in der Zukunft, oder im laufenden Monat ist noch nichts gebucht.
    active = "active"
    #: Laufender Monat, teilweise durch Buchungen gedeckt — der Rest wird noch erwartet.
    partly_used = "partly_used"
    #: Laufender Monat, die Buchungen erreichen den Planbetrag bereits.
    used = "used"
    #: Monat ist vorbei. Der Posten wirkt nicht mehr, die Zelle zeigt nur noch das Ist.
    expired = "expired"


class PlannedItemResponse(BaseModel):
    id: UUID
    service_id: UUID
    service_name: str | None = None
    partner_name: str | None = None
    period: str
    amount: Decimal
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    status: PlannedItemStatus = PlannedItemStatus.active
    #: Was von den Planposten dieses Monats noch erwartet wird. Bezieht sich auf den
    #: Monat, nicht auf den einzelnen Posten — mehrere Posten im selben Monat wirken
    #: gemeinsam gegen das Ist.
    remaining_in_month: str = "0.00"

    model_config = {"from_attributes": True}


class CreatePlannedItemRequest(BaseModel):
    service_id: UUID
    period: str = Field(pattern=PERIOD_PATTERN)
    amount: Decimal
    note: str | None = Field(default=None, max_length=500)


class UpdatePlannedItemRequest(BaseModel):
    period: str | None = Field(default=None, pattern=PERIOD_PATTERN)
    amount: Decimal | None = None
    note: str | None = Field(default=None, max_length=500)
