import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { jwtDecode } from 'jwt-decode'

export interface MandantInfo {
  id: string
  name: string
}

export interface UserInfo {
  sub: string
  role: string
  mandant_id: string | null
  exp?: number
}

interface AuthState {
  token: string | null
  user: UserInfo | null
  mandants: MandantInfo[]
  selectedMandant: MandantInfo | null

  login(token: string, mandants: MandantInfo[]): void
  selectMandant(mandant: MandantInfo, newToken: string): void
  normalize(): void
  logout(): void
}

const initialAuthState = {
  token: null,
  user: null,
  mandants: [],
  selectedMandant: null,
} satisfies Pick<AuthState, 'token' | 'user' | 'mandants' | 'selectedMandant'>

function parseJwt(token: string): UserInfo | null {
  try {
    return jwtDecode<UserInfo>(token)
  } catch {
    return null
  }
}

function isExpired(user: UserInfo | null): boolean {
  return typeof user?.exp === 'number' && user.exp * 1000 <= Date.now()
}

function sanitizeAuthState(state: Pick<AuthState, 'token' | 'user' | 'mandants' | 'selectedMandant'>) {
  if (!state.token) {
    return initialAuthState
  }

  const user = parseJwt(state.token)
  if (!user || isExpired(user)) {
    return initialAuthState
  }

  const selectedMandant = state.mandants.find((mandant) => mandant.id === user.mandant_id) ?? null

  return {
    token: state.token,
    user,
    mandants: state.mandants,
    selectedMandant,
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      ...initialAuthState,

      login(token, mandants) {
        const nextState = sanitizeAuthState({
          token,
          user: null,
          mandants,
          selectedMandant: null,
        })
        set(nextState)
      },

      selectMandant(mandant, newToken) {
        const nextState = sanitizeAuthState({
          token: newToken,
          user: null,
          mandants: useAuthStore.getState().mandants,
          selectedMandant: mandant,
        })
        set({
          ...nextState,
          selectedMandant: nextState.user?.mandant_id === mandant.id ? mandant : nextState.selectedMandant,
        })
      },

      normalize() {
        set(sanitizeAuthState(useAuthStore.getState()))
      },

      logout() {
        set(initialAuthState)
      },
    }),
    { name: 'cashflow-auth' },
  ),
)
