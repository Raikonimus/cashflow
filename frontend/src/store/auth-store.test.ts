import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from './auth-store'

function createToken(payload: Record<string, unknown>) {
  const encoded = Buffer.from(JSON.stringify(payload)).toString('base64url')
  return `header.${encoded}.signature`
}

describe('auth-store', () => {
  afterEach(() => {
    vi.useRealTimers()
    useAuthStore.setState({ token: null, user: null, mandants: [], selectedMandant: null })
    localStorage.removeItem('cashflow-auth')
  })

  it('drops invalid tokens during login', () => {
    useAuthStore.getState().login('not-a-jwt', [{ id: 'm1', name: 'Mandant 1' }])

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      mandants: [],
      selectedMandant: null,
    })
  })

  it('drops expired persisted auth state on rehydrate', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-13T20:00:00Z'))

    localStorage.setItem(
      'cashflow-auth',
      JSON.stringify({
        state: {
          token: createToken({ sub: 'u1', role: 'admin', mandant_id: 'm1', exp: 1 }),
          user: null,
          mandants: [{ id: 'm1', name: 'Mandant 1' }],
          selectedMandant: { id: 'm1', name: 'Mandant 1' },
        },
      }),
    )

    await useAuthStore.persist.rehydrate()
    useAuthStore.getState().normalize()

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      mandants: [],
      selectedMandant: null,
    })
  })
})