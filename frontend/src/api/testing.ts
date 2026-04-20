import { apiClient } from './client'

export interface JournalLineSplit {
  service_id: string
  amount: string
  assignment_mode: 'auto' | 'manual'
  amount_consistency_ok: boolean
}

export interface AssignmentTestJournalLine {
  id: string
  account_id: string
  import_run_id: string
  partner_id: string | null
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

export interface AssignmentMismatchItem {
  reason_code: string
  reason_text: string
  expected_outcome: string
  expected_partner_id: string | null
  expected_partner_name: string | null
  current_partner_id: string | null
  current_partner_name: string | null
  current_service_id: string | null
  current_service_name: string | null
  journal_line: AssignmentTestJournalLine
}

export interface PartnerAssignmentTestResponse {
  total_checked: number
  mismatches: AssignmentMismatchItem[]
}

export interface ServiceAmountConsistencyItem {
  service_id: string
  service_name: string
  partner_id: string | null
  partner_name: string | null
  positive_line_count: number
  negative_line_count: number
  lines: AssignmentTestJournalLine[]
}

export interface ServiceAmountConsistencyTestResponse {
  total_checked_services: number
  inconsistent_services: ServiceAmountConsistencyItem[]
}

export interface ServiceAmountConsistencyLineStatusResponse {
  journal_line_id: string
  split_service_id: string
  amount_consistency_ok: boolean
}

export async function runPartnerAssignmentTest(
  mandantId: string,
): Promise<PartnerAssignmentTestResponse> {
  const resp = await apiClient.post<PartnerAssignmentTestResponse>(
    `/mandants/${mandantId}/settings/tests/partner-assignment`,
  )
  return resp.data
}

export async function runServiceAmountConsistencyTest(
  mandantId: string,
): Promise<ServiceAmountConsistencyTestResponse> {
  const resp = await apiClient.post<ServiceAmountConsistencyTestResponse>(
    `/mandants/${mandantId}/settings/tests/service-amount-consistency`,
  )
  return resp.data
}

export async function setServiceAmountConsistencyLineStatus(
  mandantId: string,
  lineId: string,
  splitServiceId: string,
  isOk: boolean,
): Promise<ServiceAmountConsistencyLineStatusResponse> {
  const resp = await apiClient.post<ServiceAmountConsistencyLineStatusResponse>(
    `/mandants/${mandantId}/settings/tests/service-amount-consistency/lines/${lineId}/ok`,
    { split_service_id: splitServiceId, is_ok: isOk },
  )
  return resp.data
}
