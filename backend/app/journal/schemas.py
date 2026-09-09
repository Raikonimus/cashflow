from decimal import Decimal
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


# ─── Journal Lines ────────────────────────────────────────────────────────────

class JournalLineSplitResponse(BaseModel):
    service_id: UUID
    service_name: Optional[str] = None
    amount: Decimal
    assignment_mode: str
    amount_consistency_ok: bool


class JournalLineResponse(BaseModel):
    id: UUID
    account_id: UUID
    import_run_id: UUID
    partner_id: Optional[UUID]
    splits: list[JournalLineSplitResponse] = []
    partner_name: Optional[str] = None
    valuta_date: str
    booking_date: str
    amount: Decimal
    currency: str
    text: Optional[str]
    partner_name_raw: Optional[str]
    partner_iban_raw: Optional[str]
    partner_account_raw: Optional[str] = None
    partner_blz_raw: Optional[str] = None
    partner_bic_raw: Optional[str] = None
    unmapped_data: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedJournalResponse(BaseModel):
    items: list[JournalLineResponse]
    total: int
    page: int
    size: int
    pages: int


class JournalYearsResponse(BaseModel):
    years: list[int]
    # Jahre, die über die Prognose erreichbar sind (laufendes Jahr bis Ende des Horizonts).
    forecast_years: list[int] = []


# ─── Bulk-Assign ──────────────────────────────────────────────────────────────

class BulkAssignRequest(BaseModel):
    line_ids: list[UUID]
    partner_id: UUID


class AssignServiceRequest(BaseModel):
    service_id: UUID


SORTABLE_COLUMNS = {"valuta_date", "booking_date", "amount", "partner_name", "text", "service_name"}


class BulkAssignResponse(BaseModel):
    assigned: int
    skipped: int


class MatrixCell(BaseModel):
    gross: str
    net: str
    # True, sobald in diesen Wert eine Prognose eingeflossen ist. Im laufenden Monat
    # und in der Jahressumme kann er aus Ist und Prognose gemischt sein.
    is_forecast: bool = False


class MatrixCells(BaseModel):
    year_total: MatrixCell
    jan: MatrixCell
    feb: MatrixCell
    mar: MatrixCell
    apr: MatrixCell
    may: MatrixCell
    jun: MatrixCell
    jul: MatrixCell
    aug: MatrixCell
    sep: MatrixCell
    oct: MatrixCell
    nov: MatrixCell
    dec: MatrixCell


class IncomeExpenseServiceRow(BaseModel):
    service_id: UUID
    partner_id: UUID
    service_name: str
    partner_name: str | None = None
    service_type: str
    erfolgsneutral: bool
    cells: MatrixCells
    # Erkannte Prognoseregel — nur gesetzt, wenn der Zeitraum Prognosemonate enthält.
    forecast_rule: str | None = None
    #: 'auto' | 'manual' | 'off' — woher die Regel stammt.
    forecast_mode: str | None = None
    forecast_confidence: str | None = None
    forecast_reason: str | None = None


class IncomeExpenseGroupRow(BaseModel):
    group_id: UUID
    group_name: str
    sort_order: int
    collapsed: bool
    assigned_service_count: int
    active_years: list[int]
    subtotal_cells: MatrixCells
    services: list[IncomeExpenseServiceRow]


class IncomeExpenseSection(BaseModel):
    currency: str
    excluded_currency_count: int
    excluded_currency_amount_gross: str
    groups: list[IncomeExpenseGroupRow]
    totals: MatrixCells


class IncomeExpenseMatrixResponse(BaseModel):
    year: int
    base_currency: str
    sections: dict[str, IncomeExpenseSection]
    # Erster Monat (1–12) dieses Jahres, der prognostiziert wird; None bei reinen Ist-Jahren.
    first_forecast_month: int | None = None


# ─── Kontosalden ──────────────────────────────────────────────────────────────

class AccountBalanceRow(BaseModel):
    account_id: UUID
    account_name: str
    iban: Optional[str] = None
    currency: str
    is_active: bool
    opening_balance: str
    booked_amount: str
    current_balance: str
    line_count: int
    last_booking_date: Optional[str] = None
    foreign_currency_line_count: int = 0


class AccountBalanceTotal(BaseModel):
    currency: str
    account_count: int
    opening_balance: str
    booked_amount: str
    current_balance: str


class AccountBalancesResponse(BaseModel):
    accounts: list[AccountBalanceRow]
    totals: list[AccountBalanceTotal]


# ─── Liquidität ───────────────────────────────────────────────────────────────

class LiquidityMonth(BaseModel):
    period: str  # "YYYY-MM"
    opening_balance: str
    inflow: str
    outflow: str
    net: str
    closing_balance: str
    # Unsicherheitsband um den Endsaldo, aus den im Rückvergleich gemessenen Fehlern.
    # Nur beim Szenario "expected" belegt — siehe get_liquidity().
    closing_low: str
    closing_high: str


class LiquidityResponse(BaseModel):
    currency: str
    scenario: str = "expected"
    start_balance: str
    as_of: Optional[str] = None
    months: list[LiquidityMonth]
    lowest_balance: str
    lowest_period: Optional[str] = None
    # Tiefster Punkt des Unsicherheitsbands — die Zahl, an der sich eine Kreditlinie
    # bemisst.
    lowest_balance_low: str
    # Monatsdurchschnitt des Volumens, das die Prognose nicht abdeckt: Buchungen ohne
    # Leistungszuordnung plus Leistungen, für die mangels Historie keine Regel entstand.
    uncovered_average_per_month: str
