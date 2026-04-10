import axios from 'axios'
import { useAuthStore } from '@/store/auth-store'

export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Attach Bearer token from store on every request
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401: logout and redirect to /login
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestUrl = String(error.config?.url ?? '')
    const isAuthRequest = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/forgot-password') || requestUrl.includes('/auth/reset-password')

    if (error.response?.status === 401 && !isAuthRequest) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)
