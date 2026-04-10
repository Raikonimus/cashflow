import { apiClient } from './client'

export interface ServiceListItem {
  id: string
  partner_id: string
  name: string
  description: string | null
  service_type: 'customer' | 'supplier' | 'employee' | 'authority' | 'unknown'
  tax_rate: string
  valid_from: string | null
  valid_to: string | null
  is_base_service: boolean
  service_type_manual: boolean
  tax_rate_manual: boolean
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