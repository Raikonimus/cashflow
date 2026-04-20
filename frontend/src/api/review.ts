import { apiClient } from './client'

export type ReviewStatus = 'open' | 'confirmed' | 'adjusted' | 'rejected' | 'all'

export interface ReviewJournalLineSplit {
  service_id: string
  amount: string
  assignment_mode: 'auto' | 'manual'
  amount_consistency_ok: boolean
}

export interface ReviewJournalLine {
  id: string
  partner_id: string | null
  partner_name: string | null
  splits: ReviewJournalLineSplit[]
  valuta_date: string
  booking_date: string
  amount: string
  currency: string
  text: string | null
  partner_name_raw: string | null
  partner_iban_raw?: string | null
}

export interface ReviewServiceSummary {
  id: string
  partner_id: string
  partner_name: string | null
  name: string
  service_type: 'customer' | 'supplier' | 'employee' | 'shareholder' | 'authority' | 'unknown'
  tax_rate: string
  erfolgsneutral?: boolean
  valid_from: string | null
  valid_to: string | null
  service_type_manual: boolean
  tax_rate_manual: boolean
}

export interface NoPartnerDiagnosis {
  iban?: { provided: boolean; excluded?: boolean; found?: boolean; normalized?: string; matches_partner_iban?: boolean }
  account?: { provided: boolean; excluded?: boolean; found?: boolean; normalized?: string }
  name?: { provided: boolean; found?: boolean; value?: string }
  service_matchers?: {
    skipped?: boolean
    reason?: string
    total_matchers?: number
    matched?: number
  }
}

export interface ReviewItem {
  id: string
  mandant_id: string
  item_type: string
  journal_line_id: string | null
  service_id: string | null
  context: {
    partner_name_raw?: string
    partner_iban_raw?: string
    match_outcome?: string
    suggested_partner_id?: string
    suggested_partner_name?: string
    valuta_date?: string
    booking_date?: string
    amount?: string
    text?: string
    current_service_id?: string | null
    current_service_name?: string | null
    proposed_service_id?: string | null
    proposed_service_name?: string | null
    reason?: string
    matching_services?: string[]
    matching_service_names?: string[]
    previous_type?: string
    auto_assigned_type?: string
    auto_assigned_tax_rate?: string
    current_journal_line_ids?: string[]
    diagnosis?: NoPartnerDiagnosis
    raw_text?: string
    raw_iban?: string
    raw_account?: string
    matched_partner_ibans?: string[]
    matched_partner_iban_count?: number
  }
  status: Exclude<ReviewStatus, 'all'>
  created_at: string
  updated_at: string
  resolved_by: string | null
  resolved_at: string | null
  journal_line: ReviewJournalLine | null
  service: ReviewServiceSummary | null
  assigned_journal_lines: ReviewJournalLine[]
}

export interface PaginatedReviewItems {
  items: ReviewItem[]
  total: number
  page: number
  size: number
  pages: number
}

export interface ReviewListParams {
  status?: ReviewStatus
  page?: number
  size?: number
  itemType?: string
}

export interface ReviewArchiveParams {
  itemType?: string
  resolvedByUserId?: string
  resolvedFrom?: string
  resolvedTo?: string
  page?: number
  size?: number
}

export async function listReviewItems(
  mandantId: string,
  params: ReviewListParams = {},
): Promise<PaginatedReviewItems> {
  const {
    status = 'open',
    page = 1,
    size = 20,
    itemType,
  } = params
  const resp = await apiClient.get<PaginatedReviewItems>(
    `/mandants/${mandantId}/review`,
    { params: { status, page, size, item_type: itemType } },
  )
  return resp.data
}

export async function listReviewArchive(
  mandantId: string,
  params: ReviewArchiveParams = {},
): Promise<PaginatedReviewItems> {
  const {
    itemType,
    resolvedByUserId,
    resolvedFrom,
    resolvedTo,
    page = 1,
    size = 20,
  } = params
  const resp = await apiClient.get<PaginatedReviewItems>(
    `/mandants/${mandantId}/review/archive`,
    {
      params: {
        item_type: itemType,
        resolved_by_user_id: resolvedByUserId,
        resolved_from: resolvedFrom,
        resolved_to: resolvedTo,
        page,
        size,
      },
    },
  )
  return resp.data
}

export async function getReviewItem(
  mandantId: string,
  itemId: string,
): Promise<ReviewItem> {
  const resp = await apiClient.get<ReviewItem>(
    `/mandants/${mandantId}/review/${itemId}`,
  )
  return resp.data
}

export async function confirmReviewItem(
  mandantId: string,
  itemId: string,
): Promise<ReviewItem> {
  const resp = await apiClient.post<ReviewItem>(
    `/mandants/${mandantId}/review/${itemId}/confirm`,
  )
  return resp.data
}

export async function adjustReviewItem(
  mandantId: string,
  itemId: string,
  payload: {
    service_id?: string
    service_type?: string
    tax_rate?: string
    erfolgsneutral?: boolean
    splits?: { service_id: string; amount: string }[]
  },
): Promise<ReviewItem> {
  const resp = await apiClient.post<ReviewItem>(
    `/mandants/${mandantId}/review/${itemId}/adjust`,
    payload,
  )
  return resp.data
}

export async function rejectReviewItem(
  mandantId: string,
  itemId: string,
): Promise<ReviewItem> {
  const resp = await apiClient.post<ReviewItem>(
    `/mandants/${mandantId}/review/${itemId}/reject`,
  )
  return resp.data
}

export async function reassignReviewItem(
  mandantId: string,
  itemId: string,
  partnerId: string,
): Promise<ReviewItem> {
  const resp = await apiClient.post<ReviewItem>(
    `/mandants/${mandantId}/review/${itemId}/reassign`,
    { partner_id: partnerId },
  )
  return resp.data
}

export async function newPartnerReviewItem(
  mandantId: string,
  itemId: string,
  name: string,
): Promise<ReviewItem> {
  const resp = await apiClient.post<ReviewItem>(
    `/mandants/${mandantId}/review/${itemId}/new-partner`,
    { name },
  )
  return resp.data
}
