import { apiClient } from './client'
import type { Scenario } from './forecast'

export interface JournalLineSplit {
  service_id: string
  service_name: string | null
  amount: string
  assignment_mode: 'auto' | 'manual'
  amount_consistency_ok: boolean
}

export interface JournalLine {
  id: string
  account_id: string
  import_run_id: string
  partner_id: string | null
  partner_name: string | null
  splits: JournalLineSplit[]
  valuta_date: string
  booking_date: string
  amount: string
  currency: string
  text: string | null
  partner_name_raw: string | null
  partner_iban_raw: string | null
  partner_account_raw: string | null
  partner_blz_raw: string | null
  partner_bic_raw: string | null
  unmapped_data: Record<string, unknown> | null
  created_at: string
}

export interface PaginatedJournalLines {
  items: JournalLine[]
  total: number
  page: number
  size: number
  pages: number
}

export interface JournalYearsResponse {
  years: number[]
  /** Jahre, die über die Prognose erreichbar sind (laufendes Jahr bis Ende des Horizonts). */
  forecast_years?: number[]
}

export interface JournalFilter {
  account_id?: string
  partner_id?: string
  service_id?: string
  year?: number
  month?: number
  has_partner?: boolean
  search?: string
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
  page?: number
  size?: number
}

export interface BulkAssignResponse {
  assigned: number
  skipped: number
}

export interface AuditLogEntry {
  id: string
  event_type: string
  actor_id: string
  payload: Record<string, unknown>
  created_at: string
}

export interface PaginatedAuditLog {
  items: AuditLogEntry[]
  total: number
  page: number
  size: number
  pages: number
}

export interface MatrixCell {
  gross: string
  net: string
  /** In diesen Wert ist eine Prognose eingeflossen — er wird grau dargestellt. */
  is_forecast?: boolean
}

export interface MatrixCells {
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
}

export interface IncomeExpenseServiceRow {
  service_id: string
  partner_id: string
  service_name: string
  partner_name: string | null
  service_type: string
  erfolgsneutral: boolean
  cells: MatrixCells
  forecast_rule?: string | null
  forecast_confidence?: string | null
  forecast_reason?: string | null
}

export interface IncomeExpenseGroupRow {
  group_id: string
  group_name: string
  sort_order: number
  collapsed: boolean
  assigned_service_count: number
  active_years: number[]
  subtotal_cells: MatrixCells
  services: IncomeExpenseServiceRow[]
}

export interface IncomeExpenseSection {
  currency: string
  excluded_currency_count: number
  excluded_currency_amount_gross: string
  groups: IncomeExpenseGroupRow[]
  totals: MatrixCells
}

export interface IncomeExpenseMatrixResponse {
  year: number
  base_currency: string
  /** Erster prognostizierte Monat (1–12) dieses Jahres; null bei reinen Ist-Jahren. */
  first_forecast_month?: number | null
  sections: {
    income: IncomeExpenseSection
    expense: IncomeExpenseSection
    neutral: IncomeExpenseSection
  }
}

export async function listJournalLines(
  mandantId: string,
  filter: JournalFilter = {},
): Promise<PaginatedJournalLines> {
  const resp = await apiClient.get<PaginatedJournalLines>(`/mandants/${mandantId}/journal`, {
    params: filter,
  })
  return resp.data
}

export async function listJournalYears(
  mandantId: string,
  accountId?: string,
): Promise<JournalYearsResponse> {
  const resp = await apiClient.get<JournalYearsResponse>(`/mandants/${mandantId}/journal/years`, {
    params: accountId ? { account_id: accountId } : {},
  })
  return resp.data
}

export async function bulkAssignPartner(
  mandantId: string,
  lineIds: string[],
  partnerId: string,
): Promise<BulkAssignResponse> {
  const resp = await apiClient.post<BulkAssignResponse>(
    `/mandants/${mandantId}/journal/bulk-assign`,
    { line_ids: lineIds, partner_id: partnerId },
  )
  return resp.data
}

export async function listAuditLog(
  mandantId: string,
  page = 1,
  size = 20,
): Promise<PaginatedAuditLog> {
  const resp = await apiClient.get<PaginatedAuditLog>(`/mandants/${mandantId}/audit`, {
    params: { page, size },
  })
  return resp.data
}

export async function getIncomeExpenseMatrix(
  mandantId: string,
  year: number,
  scenario: Scenario = 'expected',
): Promise<IncomeExpenseMatrixResponse> {
  const resp = await apiClient.get<IncomeExpenseMatrixResponse>(
    `/mandants/${mandantId}/reports/income-expense`,
    { params: { year, scenario } },
  )
  return resp.data
}

// ─── Kontosalden ──────────────────────────────────────────────────────────────

export interface AccountBalanceRow {
  account_id: string
  account_name: string
  iban: string | null
  currency: string
  is_active: boolean
  opening_balance: string
  booked_amount: string
  current_balance: string
  line_count: number
  last_booking_date: string | null
  foreign_currency_line_count: number
}

export interface AccountBalanceTotal {
  currency: string
  account_count: number
  opening_balance: string
  booked_amount: string
  current_balance: string
}

export interface AccountBalancesResponse {
  accounts: AccountBalanceRow[]
  totals: AccountBalanceTotal[]
}

export async function getAccountBalances(mandantId: string): Promise<AccountBalancesResponse> {
  const resp = await apiClient.get<AccountBalancesResponse>(
    `/mandants/${mandantId}/reports/account-balances`,
  )
  return resp.data
}

// ─── Liquiditätsvorschau ──────────────────────────────────────────────────────

export interface LiquidityMonth {
  period: string
  opening_balance: string
  inflow: string
  outflow: string
  net: string
  closing_balance: string
  /** Unsicherheitsband aus den gemessenen Prognosefehlern. Nur bei scenario='expected'
   *  weicht es vom Endsaldo ab — bei einem Stresstest wäre es doppelt gezählt. */
  closing_low: string
  closing_high: string
}

export interface LiquidityResponse {
  currency: string
  scenario: Scenario
  start_balance: string
  as_of: string | null
  months: LiquidityMonth[]
  lowest_balance: string
  lowest_period: string | null
  /** Tiefster Punkt des Unsicherheitsbands — die Zahl für die Kreditlinie. */
  lowest_balance_low: string
  uncovered_average_per_month: string
}

export async function getLiquidity(
  mandantId: string,
  scenario: Scenario = 'expected',
): Promise<LiquidityResponse> {
  const resp = await apiClient.get<LiquidityResponse>(`/mandants/${mandantId}/reports/liquidity`, {
    params: { scenario },
  })
  return resp.data
}
