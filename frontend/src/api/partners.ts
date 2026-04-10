import { apiClient } from './client'

export interface PartnerListItem {
  id: string
  name: string
  display_name: string | null
  is_active: boolean
  iban_count: number
  name_count: number
  pattern_count: number
  journal_line_count: number
  created_at: string
}

export interface PartnerDetail {
  id: string
  mandant_id: string
  name: string
  display_name: string | null
  is_active: boolean
  ibans: PartnerIban[]
  accounts: PartnerAccount[]
  names: PartnerName[]
  patterns: PartnerPattern[]
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

export interface PartnerPattern {
  id: string
  pattern: string
  pattern_type: 'string' | 'regex'
  match_field: 'description' | 'partner_name' | 'partner_iban'
  created_at: string
}

export interface PaginatedPartners {
  items: PartnerListItem[]
  total: number
  page: number
  size: number
  pages: number
}

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
): Promise<PaginatedPartners> {
  const resp = await apiClient.get<PaginatedPartners>(
    `/mandants/${mandantId}/partners`,
    { params: { page, size, include_inactive: includeInactive, search } },
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

export async function getPartnerNeighbors(
  mandantId: string,
  partnerId: string,
): Promise<PartnerNeighbors> {
  const resp = await apiClient.get<PartnerNeighbors>(
    `/mandants/${mandantId}/partners/${partnerId}/neighbors`,
  )
  return resp.data
}

export async function previewPattern(
  mandantId: string,
  partnerId: string,
  pattern: string,
  patternType: 'string' | 'regex',
  matchField: 'partner_name' | 'partner_iban' | 'description',
): Promise<PartnerNeighbor[]> {
  const resp = await apiClient.post<PartnerNeighbor[]>(
    `/mandants/${mandantId}/partners/${partnerId}/patterns/preview`,
    { pattern, pattern_type: patternType, match_field: matchField },
  )
  return resp.data
}

export async function createPartner(
  mandantId: string,
  name: string,
): Promise<PartnerDetail> {
  const resp = await apiClient.post<PartnerDetail>(
    `/mandants/${mandantId}/partners`,
    { name },
  )
  return resp.data
}

export async function addPartnerIban(
  mandantId: string,
  partnerId: string,
  iban: string,
): Promise<PartnerIban> {
  const resp = await apiClient.post<PartnerIban>(
    `/mandants/${mandantId}/partners/${partnerId}/ibans`,
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

export async function addPartnerPattern(
  mandantId: string,
  partnerId: string,
  data: { pattern: string; pattern_type: 'string' | 'regex'; match_field: string },
): Promise<PartnerPattern> {
  const resp = await apiClient.post<PartnerPattern>(
    `/mandants/${mandantId}/partners/${partnerId}/patterns`,
    data,
  )
  return resp.data
}

export async function deletePartnerPattern(
  mandantId: string,
  partnerId: string,
  patternId: string,
): Promise<void> {
  await apiClient.delete(
    `/mandants/${mandantId}/partners/${partnerId}/patterns/${patternId}`,
  )
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
