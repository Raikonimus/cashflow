import { apiClient } from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
  mandants: Array<{ id: string; name: string }>
  requires_mandant_selection: boolean
}

export interface SelectMandantResponse {
  access_token: string
  token_type: string
}

export async function loginUser(email: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/login', { email, password })
  return data
}

export async function selectMandant(mandantId: string): Promise<SelectMandantResponse> {
  const { data } = await apiClient.post<SelectMandantResponse>('/auth/select-mandant', {
    mandant_id: mandantId,
  })
  return data
}

export async function forgotPassword(email: string): Promise<void> {
  await apiClient.post('/auth/forgot-password', { email })
}

export async function logoutUser(): Promise<void> {
  await apiClient.post('/auth/logout')
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await apiClient.post('/auth/reset-password', { token, new_password: newPassword })
}
