import { apiClient } from './client'

export type ServiceType = 'customer' | 'supplier' | 'employee' | 'shareholder' | 'authority' | 'internal_transfer' | 'unknown'
export type KeywordTargetType = 'employee' | 'shareholder' | 'authority'
export type ServiceGroupSection = 'income' | 'expense' | 'neutral'

export interface ServiceListItem {
  id: string
  partner_id: string
  name: string
  description: string | null
  service_type: ServiceType
  tax_rate: string
  erfolgsneutral: boolean
  valid_from: string | null
  valid_to: string | null
  is_base_service: boolean
  service_type_manual: boolean
  tax_rate_manual: boolean
  created_at: string
  updated_at: string
  journal_line_count: number
  matchers: ServiceMatcherItem[]
}

export interface ServiceMatcherItem {
  id: string
  pattern: string
  pattern_type: 'string' | 'regex'
  internal_only: boolean
  created_at: string
  updated_at: string
}

export interface CreateServicePayload {
  name: string
  description?: string | null
  service_type?: ServiceType
  tax_rate?: string
  erfolgsneutral?: boolean
  valid_from?: string | null
  valid_to?: string | null
}

export interface UpdateServicePayload {
  name?: string
  description?: string | null
  service_type?: ServiceType
  tax_rate?: string
  erfolgsneutral?: boolean
  valid_from?: string | null
  valid_to?: string | null
}

export interface CreateServiceMatcherPayload {
  pattern: string
  pattern_type: 'string' | 'regex'
  internal_only?: boolean
}

export interface UpdateServiceMatcherPayload {
  pattern?: string
  pattern_type?: 'string' | 'regex'
  internal_only?: boolean
}

export interface ServiceTypeKeywordItem {
  id: string
  mandant_id: string | null
  pattern: string
  pattern_type: 'string' | 'regex'
  target_service_type: KeywordTargetType
  created_at: string
  updated_at: string
}

export interface SystemServiceTypeKeywordItem {
  pattern: string
  pattern_type: 'string' | 'regex'
  target_service_type: KeywordTargetType
}

export interface ServiceTypeKeywordListResponse {
  items: ServiceTypeKeywordItem[]
  system_defaults: SystemServiceTypeKeywordItem[]
}

export interface CreateServiceTypeKeywordPayload {
  pattern: string
  pattern_type: 'string' | 'regex'
  target_service_type: KeywordTargetType
}

export interface UpdateServiceTypeKeywordPayload {
  pattern?: string
  pattern_type?: 'string' | 'regex'
  target_service_type?: KeywordTargetType
}

export interface ServiceGroupItem {
  id: string
  mandant_id: string
  section: ServiceGroupSection
  name: string
  sort_order: number
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface CreateServiceGroupPayload {
  section: ServiceGroupSection
  name: string
  sort_order?: number
}

export interface UpdateServiceGroupPayload {
  name?: string
  sort_order?: number
}

export interface DeleteServiceGroupPayload {
  reassign_to_group_id?: string
}

export interface ServiceGroupAssignmentItem {
  id: string
  mandant_id: string
  service_id: string
  service_group_id: string
  created_at: string
  updated_at: string
}

export async function listPartnerServices(
  mandantId: string,
  partnerId: string,
): Promise<ServiceListItem[]> {
  const resp = await apiClient.get<ServiceListItem[]>(
    `/mandants/${mandantId}/partners/${partnerId}/services`,
  )
  return resp.data
}

export async function createPartnerService(
  mandantId: string,
  partnerId: string,
  payload: CreateServicePayload,
): Promise<ServiceListItem> {
  const resp = await apiClient.post<ServiceListItem>(
    `/mandants/${mandantId}/partners/${partnerId}/services`,
    payload,
  )
  return resp.data
}

export async function updateService(
  mandantId: string,
  serviceId: string,
  payload: UpdateServicePayload,
): Promise<ServiceListItem> {
  const resp = await apiClient.patch<ServiceListItem>(
    `/mandants/${mandantId}/services/${serviceId}`,
    payload,
  )
  return resp.data
}

export async function deleteService(
  mandantId: string,
  serviceId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/services/${serviceId}`)
}

export async function createServiceMatcher(
  mandantId: string,
  serviceId: string,
  payload: CreateServiceMatcherPayload,
): Promise<ServiceMatcherItem> {
  const resp = await apiClient.post<ServiceMatcherItem>(
    `/mandants/${mandantId}/services/${serviceId}/matchers`,
    payload,
  )
  return resp.data
}

export async function updateServiceMatcher(
  mandantId: string,
  serviceId: string,
  matcherId: string,
  payload: UpdateServiceMatcherPayload,
): Promise<ServiceMatcherItem> {
  const resp = await apiClient.patch<ServiceMatcherItem>(
    `/mandants/${mandantId}/services/${serviceId}/matchers/${matcherId}`,
    payload,
  )
  return resp.data
}

export async function deleteServiceMatcher(
  mandantId: string,
  serviceId: string,
  matcherId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/services/${serviceId}/matchers/${matcherId}`)
}

export interface MatcherPreviewLineItem {
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
}

export interface MatcherPreviewResponse {
  matched_lines: MatcherPreviewLineItem[]
  total: number
}

export async function previewServiceMatcher(
  mandantId: string,
  serviceId: string,
  payload: CreateServiceMatcherPayload,
): Promise<MatcherPreviewResponse> {
  const resp = await apiClient.post<MatcherPreviewResponse>(
    `/mandants/${mandantId}/services/${serviceId}/matchers/preview`,
    payload,
  )
  return resp.data
}

export async function listServiceKeywords(
  mandantId: string,
): Promise<ServiceTypeKeywordListResponse> {
  const resp = await apiClient.get<ServiceTypeKeywordListResponse>(
    `/mandants/${mandantId}/settings/service-keywords`,
  )
  return resp.data
}

export async function createServiceKeyword(
  mandantId: string,
  payload: CreateServiceTypeKeywordPayload,
): Promise<ServiceTypeKeywordItem> {
  const resp = await apiClient.post<ServiceTypeKeywordItem>(
    `/mandants/${mandantId}/settings/service-keywords`,
    payload,
  )
  return resp.data
}

export async function updateServiceKeyword(
  mandantId: string,
  keywordId: string,
  payload: UpdateServiceTypeKeywordPayload,
): Promise<ServiceTypeKeywordItem> {
  const resp = await apiClient.patch<ServiceTypeKeywordItem>(
    `/mandants/${mandantId}/settings/service-keywords/${keywordId}`,
    payload,
  )
  return resp.data
}

export async function deleteServiceKeyword(
  mandantId: string,
  keywordId: string,
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/settings/service-keywords/${keywordId}`)
}

export async function listServiceGroups(
  mandantId: string,
  section: ServiceGroupSection,
): Promise<ServiceGroupItem[]> {
  const resp = await apiClient.get<ServiceGroupItem[]>(
    `/mandants/${mandantId}/service-groups`,
    { params: { section } },
  )
  return resp.data
}

export async function createServiceGroup(
  mandantId: string,
  payload: CreateServiceGroupPayload,
): Promise<ServiceGroupItem> {
  const resp = await apiClient.post<ServiceGroupItem>(
    `/mandants/${mandantId}/service-groups`,
    payload,
  )
  return resp.data
}

export async function updateServiceGroup(
  mandantId: string,
  groupId: string,
  payload: UpdateServiceGroupPayload,
): Promise<ServiceGroupItem> {
  const resp = await apiClient.patch<ServiceGroupItem>(
    `/mandants/${mandantId}/service-groups/${groupId}`,
    payload,
  )
  return resp.data
}

export async function deleteServiceGroup(
  mandantId: string,
  groupId: string,
  payload: DeleteServiceGroupPayload = {},
): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/service-groups/${groupId}`, { data: payload })
}

export async function assignServiceGroup(
  mandantId: string,
  serviceId: string,
  serviceGroupId: string,
): Promise<ServiceGroupAssignmentItem> {
  const resp = await apiClient.post<ServiceGroupAssignmentItem>(
    `/mandants/${mandantId}/services/${serviceId}/group-assignment`,
    { service_group_id: serviceGroupId },
  )
  return resp.data
}