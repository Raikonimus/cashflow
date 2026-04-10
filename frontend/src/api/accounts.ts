import { apiClient } from './client'

export interface AccountListItem {
  id: string
  mandant_id: string
  name: string
  iban?: string | null
  currency?: string
  is_active?: boolean
  has_column_mapping?: boolean
  created_at: string
}

export interface CreateAccountRequest {
  name: string
  iban?: string | null
  currency?: string
}

// ─── Column-Mapping ───────────────────────────────────────────────────────────

export interface ColumnAssignment {
  source: string      // Name der CSV-Spalte
  target: string      // valuta_date | booking_date | amount | partner_iban | partner_name | description | unused
  sort_order: number  // Reihenfolge bei Mehrfach-Belegung
}

export interface ColumnMapping {
  id?: string
  account_id?: string
  column_assignments: ColumnAssignment[] | null
  // Legacy-Felder (werden aus column_assignments abgeleitet)
  valuta_date_col: string | null
  booking_date_col: string | null
  amount_col: string | null
  partner_name_col: string | null
  partner_iban_col: string | null
  description_col: string | null
  // Parser-Konfiguration
  decimal_separator: string
  date_format: string
  delimiter: string
  encoding: string
  skip_rows: number
}

export type SaveMappingRequest = Partial<Omit<ColumnMapping, 'id' | 'account_id'>>

// ─── Account CRUD ─────────────────────────────────────────────────────────────

export async function listAccounts(mandantId: string): Promise<AccountListItem[]> {
  const resp = await apiClient.get<AccountListItem[]>(
    `/mandants/${mandantId}/accounts`,
  )
  return resp.data
}

export async function createAccount(
  mandantId: string,
  data: CreateAccountRequest,
): Promise<AccountListItem> {
  const resp = await apiClient.post<AccountListItem>(
    `/mandants/${mandantId}/accounts`,
    data,
  )
  return resp.data
}

// ─── Column-Mapping CRUD ──────────────────────────────────────────────────────

export async function getMapping(
  mandantId: string,
  accountId: string,
): Promise<ColumnMapping | null> {
  try {
    const resp = await apiClient.get<ColumnMapping>(
      `/mandants/${mandantId}/accounts/${accountId}/column-mapping`,
    )
    return resp.data
  } catch (err: any) {
    if (err?.response?.status === 404) return null
    throw err
  }
}

export async function saveMapping(
  mandantId: string,
  accountId: string,
  data: SaveMappingRequest,
): Promise<ColumnMapping> {
  const resp = await apiClient.put<ColumnMapping>(
    `/mandants/${mandantId}/accounts/${accountId}/column-mapping`,
    data,
  )
  return resp.data
}

// ─── Excluded Identifiers ─────────────────────────────────────────────────────

export interface ExcludedIdentifier {
  id: string
  account_id: string
  identifier_type: 'iban' | 'account_number'
  value: string
  label: string | null
  created_at: string
}

export interface ExcludedIdentifierCreate {
  identifier_type: 'iban' | 'account_number'
  value: string
  label?: string | null
}

export async function listExcludedIdentifiers(
  mandantId: string,
  accountId: string,
): Promise<ExcludedIdentifier[]> {
  const resp = await apiClient.get<ExcludedIdentifier[]>(
    `/mandants/${mandantId}/accounts/${accountId}/excluded-identifiers`,
  )
  return resp.data
}

export async function addExcludedIdentifier(
  mandantId: string,
  accountId: string,
  data: ExcludedIdentifierCreate,
): Promise<ExcludedIdentifier> {
  const resp = await apiClient.post<ExcludedIdentifier>(
    `/mandants/${mandantId}/accounts/${accountId}/excluded-identifiers`,
    data,
  )
  return resp.data
}

export async function deleteExcludedIdentifier(
  mandantId: string,
  accountId: string,
  identifierId: string,
): Promise<void> {
  await apiClient.delete(
    `/mandants/${mandantId}/accounts/${accountId}/excluded-identifiers/${identifierId}`,
  )
}

export interface ApplyExcludedResult {
  affected: number
  message: string
}

export async function applyExcludedIdentifiers(
  mandantId: string,
  accountId: string,
): Promise<ApplyExcludedResult> {
  const resp = await apiClient.post<ApplyExcludedResult>(
    `/mandants/${mandantId}/accounts/${accountId}/excluded-identifiers/apply`,
  )
  return resp.data
}


export interface CsvPreviewResult {
  columns: string[]
  detected_delimiter: string | null
  detected_encoding: string | null
  sample_rows: Record<string, string>[]
}

export async function previewCsvColumns(
  mandantId: string,
  accountId: string,
  file: File,
  delimiter = ';',
  encoding = 'utf-8',
  skipRows = 0,
): Promise<CsvPreviewResult> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({
    delimiter,
    encoding,
    skip_rows: String(skipRows),
  })
  const resp = await apiClient.post<CsvPreviewResult>(
    `/mandants/${mandantId}/accounts/${accountId}/column-mapping/preview?${params}`,
    form,
    { headers: { 'Content-Type': undefined } },
  )
  return resp.data
}
