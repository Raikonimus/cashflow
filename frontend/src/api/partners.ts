import { apiClient } from './client'
import type { ServiceType } from './services'

export interface PartnerListItem {
  id: string
  name: string
  display_name: string | null
  is_active: boolean
  manual_assignment: boolean
  service_types: Array<'customer' | 'supplier' | 'employee' | 'shareholder' | 'authority' | 'unknown'>
  iban_count: number
  name_count: number
  journal_line_count: number
  created_at: string
}

export interface PartnerDetail {
  id: string
  mandant_id: string
  name: string
  display_name: string | null
  is_active: boolean
  manual_assignment: boolean
  ibans: PartnerIban[]
  accounts: PartnerAccount[]
  names: PartnerName[]
  created_at: string
  updated_at: string
}

export interface PartnerIban {
  id: string
  partner_id: string
  iban: string
  created_at: string
}

export interface PartnerAccount {
  id: string
  blz: string | null
  account_number: string
  bic: string | null
  created_at: string
}

export interface PartnerName {
  id: string
  partner_id: string
  name: string
  created_at: string
}

export interface PaginatedPartners {
  items: PartnerListItem[]
  total: number
  page: number
  size: number
  pages: number
}

export type PartnerSortField = 'name' | 'iban_count' | 'name_count' | 'journal_line_count' | 'status'
export type SortDirection = 'asc' | 'desc'

export interface MergeResponse {
  target: PartnerDetail
  lines_reassigned: number
  audit_log_id: string
}

export interface PartnerNeighbor {
  id: string
  name: string
}

export interface PartnerNeighbors {
  prev: PartnerNeighbor | null
  next: PartnerNeighbor | null
}

export async function listPartners(
  mandantId: string,
  page = 1,
  size = 20,
  includeInactive = false,
  search = '',
  serviceType?: ServiceType,
  sortBy: PartnerSortField = 'name',
  sortDir: SortDirection = 'asc',
): Promise<PaginatedPartners> {
  const resp = await apiClient.get<PaginatedPartners>(
    `/mandants/${mandantId}/partners`,
    { params: { page, size, include_inactive: includeInactive, search, service_type: serviceType, sort_by: sortBy, sort_dir: sortDir } },
  )
  return resp.data
}

export async function getPartner(
  mandantId: string,
  partnerId: string,
): Promise<PartnerDetail> {
  const resp = await apiClient.get<PartnerDetail>(
    `/mandants/${mandantId}/partners/${partnerId}`,
  )
  return resp.data
}

export async function updatePartnerDisplayName(
  mandantId: string,
  partnerId: string,
  displayName: string | null,
): Promise<PartnerDetail> {
  const resp = await apiClient.patch<PartnerDetail>(
    `/mandants/${mandantId}/partners/${partnerId}`,
    { display_name: displayName },
  )
  return resp.data
}

export async function updatePartner(
  mandantId: string,
  partnerId: string,
  payload: { display_name?: string | null; manual_assignment?: boolean },
): Promise<PartnerDetail> {
  const resp = await apiClient.patch<PartnerDetail>(
    `/mandants/${mandantId}/partners/${partnerId}`,
    payload,
  )
  return resp.data
}

export async function deletePartner(
  mandantId: string,
  partnerId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/partners/${partnerId}`)
}

export async function getPartnerNeighbors(
  mandantId: string,
  partnerId: string,
): Promise<PartnerNeighbors> {
  const resp = await apiClient.get<PartnerNeighbors>(
    `/mandants/${mandantId}/partners/${partnerId}/neighbors`,
  )
  return resp.data
}

export async function createPartner(
  mandantId: string,
  name: string,
  manualAssignment = false,
): Promise<PartnerDetail> {
  const resp = await apiClient.post<PartnerDetail>(
    `/mandants/${mandantId}/partners`,
    { name, manual_assignment: manualAssignment },
  )
  return resp.data
}

export async function addPartnerIban(
  mandantId: string,
  partnerId: string,
  iban: string,
  reassign = false,
): Promise<PartnerIban> {
  const resp = await apiClient.post<PartnerIban>(
    `/mandants/${mandantId}/partners/${partnerId}/ibans`,
    { iban },
    { params: reassign ? { reassign: true } : undefined },
  )
  return resp.data
}

export async function previewPartnerIban(
  mandantId: string,
  partnerId: string,
  iban: string,
): Promise<AccountPreviewResponse> {
  const resp = await apiClient.post<AccountPreviewResponse>(
    `/mandants/${mandantId}/partners/${partnerId}/ibans/preview`,
    { iban },
  )
  return resp.data
}

export async function deletePartnerIban(
  mandantId: string,
  partnerId: string,
  ibanId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/partners/${partnerId}/ibans/${ibanId}`)
}

export interface AccountPreviewLineItem {
  journal_line_id: string
  partner_name_raw: string | null
  current_partner_name: string | null
  current_service_name: string | null
  has_conflicting_partner_criteria: boolean
  conflicting_partner_criteria: string[]
  booking_date: string
  valuta_date: string
  amount: string
  currency: string
  text: string | null
  already_assigned: boolean
}

export interface AccountPreviewResponse {
  matched_lines: AccountPreviewLineItem[]
  total: number
}

export async function previewPartnerAccount(
  mandantId: string,
  partnerId: string,
  data: { account_number: string; blz?: string },
): Promise<AccountPreviewResponse> {
  const resp = await apiClient.post<AccountPreviewResponse>(
    `/mandants/${mandantId}/partners/${partnerId}/accounts/preview`,
    data,
  )
  return resp.data
}

export async function addPartnerAccount(
  mandantId: string,
  partnerId: string,
  data: { account_number: string; blz?: string; bic?: string },
  reassign = false,
): Promise<PartnerAccount> {
  const resp = await apiClient.post<PartnerAccount>(
    `/mandants/${mandantId}/partners/${partnerId}/accounts`,
    data,
    { params: reassign ? { reassign: true } : undefined },
  )
  return resp.data
}

export async function deletePartnerAccount(
  mandantId: string,
  partnerId: string,
  accountId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/partners/${partnerId}/accounts/${accountId}`)
}

export async function addPartnerName(
  mandantId: string,
  partnerId: string,
  name: string,
): Promise<PartnerName> {
  const resp = await apiClient.post<PartnerName>(
    `/mandants/${mandantId}/partners/${partnerId}/names`,
    { name },
  )
  return resp.data
}

export async function deletePartnerName(
  mandantId: string,
  partnerId: string,
  nameId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/partners/${partnerId}/names/${nameId}`)
}

export async function mergePartners(
  mandantId: string,
  sourceId: string,
  targetId: string,
): Promise<MergeResponse> {
  const resp = await apiClient.post<MergeResponse>(
    `/mandants/${mandantId}/partners/merge`,
    { source_partner_id: sourceId, target_partner_id: targetId },
  )
  return resp.data
}
