import { apiClient } from './client'

export interface AssignmentTestJournalLine {
  id: string
  account_id: string
  import_run_id: string
  partner_id: string | null
  service_id: string | null
  service_assignment_mode: string | null
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

export async function runPartnerAssignmentTest(
  mandantId: string,
): Promise<PartnerAssignmentTestResponse> {
  const resp = await apiClient.post<PartnerAssignmentTestResponse>(
    `/mandants/${mandantId}/settings/tests/partner-assignment`,
  )
  return resp.data
}
