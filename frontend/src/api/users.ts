import { apiClient } from './client'

export interface UserListItem {
  id: string
  email: string
  role: string
  is_active: boolean
  invitation_status: string
  created_at?: string
}

export interface CreateUserRequest {
  email: string
  role: string
}

export interface UpdateUserRequest {
  is_active?: boolean
  role?: string
}

export interface MandantListItem {
  id: string
  name: string
  is_active: boolean
  created_at: string
}

export interface CleanupPreviewItem {
  key: string
  label: string
  count: number
}

export interface CleanupPreviewSection {
  key: string
  label: string
  description: string
  items: CleanupPreviewItem[]
}

export interface MandantCleanupPreview {
  mandant_id: string
  mandant_name: string
  delete_mandant: CleanupPreviewSection
  delete_data: CleanupPreviewSection
  selectable_sections: CleanupPreviewSection[]
}

export interface ExecuteMandantCleanupPayload {
  mode: 'delete_mandant' | 'delete_data' | 'selected'
  scopes?: Array<'journal_data' | 'partner_service_data' | 'audit_data' | 'review_data'>
}

export interface ExecuteMandantCleanupResult {
  mode: 'delete_mandant' | 'delete_data' | 'selected'
  deleted_mandant: boolean
  executed_sections: string[]
  items: CleanupPreviewItem[]
}

export interface CreateMandantRequest {
  name: string
}

export interface MandantUserAssignment {
  mandant_id: string
  user_id: string
}

export async function listUsers(): Promise<UserListItem[]> {
  const resp = await apiClient.get<UserListItem[]>('/users')
  return resp.data
}

export async function createUser(data: CreateUserRequest): Promise<UserListItem> {
  const resp = await apiClient.post<UserListItem>('/users', data)
  return resp.data
}

export async function updateUser(id: string, data: UpdateUserRequest): Promise<UserListItem> {
  const resp = await apiClient.patch<UserListItem>(`/users/${id}`, data)
  return resp.data
}

export async function deleteUser(id: string): Promise<void> {
  await apiClient.delete(`/users/${id}`)
}

export async function listMandants(): Promise<MandantListItem[]> {
  const resp = await apiClient.get<MandantListItem[]>('/mandants')
  return resp.data
}

export async function createMandant(data: CreateMandantRequest): Promise<MandantListItem> {
  const resp = await apiClient.post<MandantListItem>('/mandants', data)
  return resp.data
}

export async function getMandantCleanupPreview(mandantId: string): Promise<MandantCleanupPreview> {
  const resp = await apiClient.get<MandantCleanupPreview>(`/mandants/${mandantId}/cleanup-preview`)
  return resp.data
}

export async function executeMandantCleanup(
  mandantId: string,
  data: ExecuteMandantCleanupPayload,
): Promise<ExecuteMandantCleanupResult> {
  const resp = await apiClient.post<ExecuteMandantCleanupResult>(`/mandants/${mandantId}/cleanup`, data)
  return resp.data
}

export async function assignUserToMandant(
  mandantId: string,
  userId: string,
): Promise<void> {
  await apiClient.post(`/mandants/${mandantId}/users`, { user_id: userId })
}
