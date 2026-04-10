import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface MandantInfo {
  id: string
  name: string
}

export interface UserInfo {
  sub: string
  role: string
  mandant_id: string | null
}

interface AuthState {
  token: string | null
  user: UserInfo | null
  mandants: MandantInfo[]
  selectedMandant: MandantInfo | null

  login(token: string, mandants: MandantInfo[]): void
  selectMandant(mandant: MandantInfo, newToken: string): void
  logout(): void
}

function parseJwt(token: string): UserInfo | null {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload)) as UserInfo
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      mandants: [],
      selectedMandant: null,

      login(token, mandants) {
        set({ token, user: parseJwt(token), mandants, selectedMandant: null })
      },

      selectMandant(mandant, newToken) {
        set({
          token: newToken,
          user: parseJwt(newToken),
          selectedMandant: mandant,
        })
      },

      logout() {
        set({ token: null, user: null, mandants: [], selectedMandant: null })
      },
    }),
    { name: 'cashflow-auth' },
  ),
)
