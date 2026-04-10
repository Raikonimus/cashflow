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

export async function assignUserToMandant(
  mandantId: string,
  userId: string,
): Promise<void> {
  await apiClient.post(`/mandants/${mandantId}/users`, { user_id: userId })
}
