import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestJwt } from './jwt'

export const handlers = [
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as Record<string, string>
    if (body.email === 'test@example.com' && body.password === 'password') {
      return HttpResponse.json({
        access_token: createTestJwt({ sub: 'user-1', role: 'accountant', mandant_id: 'mandant-1' }),
        token_type: 'bearer',
        mandants: [{ id: 'mandant-1', name: 'Test Mandant' }],
        requires_mandant_selection: false,
      })
    }
    if (body.email === 'multi@example.com' && body.password === 'password') {
      return HttpResponse.json({
        access_token: createTestJwt({ sub: 'user-1', role: 'accountant', mandant_id: null }),
        token_type: 'bearer',
        mandants: [
          { id: 'mandant-1', name: 'Mandant A' },
          { id: 'mandant-2', name: 'Mandant B' },
        ],
        requires_mandant_selection: true,
      })
    }
    return HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 })
  }),

  http.post('/api/v1/auth/select-mandant', async () => {
    return HttpResponse.json({
      access_token: createTestJwt({ sub: 'user-1', role: 'accountant', mandant_id: 'mandant-1' }),
      token_type: 'bearer',
    })
  }),

  http.post('/api/v1/auth/forgot-password', async () => {
    return HttpResponse.json({ message: 'OK' })
  }),

  http.post('/api/v1/auth/reset-password', async ({ request }) => {
    const body = (await request.json()) as Record<string, string>
    if (body.token === 'valid-token') {
      return HttpResponse.json({ message: 'Password reset successful' })
    }
    return HttpResponse.json({ detail: 'Invalid or expired token' }, { status: 400 })
  }),
]

export const server = setupServer(...handlers)
