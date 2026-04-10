import { apiClient } from './client'

export interface ImportRunListItem {
  id: string
  filename: string
  row_count: number
  skipped_count: number
  error_count: number
  status: string
  created_at: string
  completed_at: string | null
}

export interface ImportDuplicateInfo {
  row: number | null
  valuta_date: string
  booking_date: string
  amount: string
  text: string | null
  partner_name_raw: string | null
}

export interface ImportErrorDetails {
  parse_errors?: Array<{ row: number; error: string }>
  duplicates?: ImportDuplicateInfo[]
}

export interface ImportRunDetail extends ImportRunListItem {
  account_id: string
  user_id: string
  error_details: ImportErrorDetails | null
}

export interface PaginatedImportRuns {
  items: ImportRunListItem[]
  total: number
  page: number
  size: number
  pages: number
}

export async function uploadCsv(
  mandantId: string,
  accountId: string,
  files: File[],
): Promise<ImportRunDetail[]> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const resp = await apiClient.post<ImportRunDetail[]>(
    `/mandants/${mandantId}/accounts/${accountId}/imports`,
    form,
    { headers: { 'Content-Type': undefined } },
  )
  return resp.data
}

export async function listImportRuns(
  mandantId: string,
  accountId: string,
  page = 1,
  size = 20,
): Promise<PaginatedImportRuns> {
  const resp = await apiClient.get<PaginatedImportRuns>(
    `/mandants/${mandantId}/accounts/${accountId}/imports`,
    { params: { page, size } },
  )
  return resp.data
}
