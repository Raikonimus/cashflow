import { apiClient } from './client'

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
  const resp = await apiClient.get<PaginatedJournalLines>(
    `/mandants/${mandantId}/journal`,
    { params: filter },
  )
  return resp.data
}

export async function listJournalYears(
  mandantId: string,
  accountId?: string,
): Promise<JournalYearsResponse> {
  const resp = await apiClient.get<JournalYearsResponse>(
    `/mandants/${mandantId}/journal/years`,
    { params: accountId ? { account_id: accountId } : {} },
  )
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
  const resp = await apiClient.get<PaginatedAuditLog>(
    `/mandants/${mandantId}/audit`,
    { params: { page, size } },
  )
  return resp.data
}

export async function getIncomeExpenseMatrix(
  mandantId: string,
  year: number,
): Promise<IncomeExpenseMatrixResponse> {
  const resp = await apiClient.get<IncomeExpenseMatrixResponse>(
    `/mandants/${mandantId}/reports/income-expense`,
    { params: { year } },
  )
  return resp.data
}
