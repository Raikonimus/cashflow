import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { createTestJwt } from '@/test/jwt'
import { useAuthStore, type MandantInfo } from '@/store/auth-store'
import { MandantSwitcher } from './MandantSwitcher'

const MANDANT_A = { id: 'mandant-1', name: 'Mandant A' }
const MANDANT_B = { id: 'mandant-2', name: 'Mandant B' }

/** Setzt den Anmeldezustand und zeichnet den Wechsler. */
function zeichne(mandants: MandantInfo[], aktiv: MandantInfo | null) {
  act(() => {
    useAuthStore.setState({
      token: createTestJwt({
        sub: 'u1',
        role: 'accountant',
        mandant_id: aktiv?.id ?? null,
      }),
      user: { sub: 'u1', role: 'accountant', mandant_id: aktiv?.id ?? null },
      mandants,
      selectedMandant: aktiv,
    })
  })

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    qc,
    ...render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <MandantSwitcher />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('MandantSwitcher', () => {
  afterEach(() => {
    act(() => {
      useAuthStore.setState({
        token: null,
        user: null,
        mandants: [],
        selectedMandant: null,
      })
    })
  })

  it('zeigt bei einem Mandanten nur den Namen, ohne Menü', () => {
    // Ein Menü mit einem Eintrag, der schon aktiv ist, wäre eine Schaltfläche, die
    // nichts tut.
    zeichne([MANDANT_A], MANDANT_A)

    expect(screen.getByText('Mandant A')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('zeigt bei mehreren Mandanten ein Menü mit allen', async () => {
    zeichne([MANDANT_A, MANDANT_B], MANDANT_A)

    fireEvent.click(screen.getByRole('button', { name: /mandant wechseln/i }))

    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Mandant B/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Mandant A.*aktiv/ })).toBeInTheDocument()
  })

  it('wechselt den Mandanten und übernimmt das neue Token', async () => {
    server.use(
      http.post('/api/v1/auth/select-mandant', async ({ request }) => {
        const body = (await request.json()) as Record<string, string>
        expect(body.mandant_id).toBe('mandant-2')
        return HttpResponse.json({
          access_token: createTestJwt({
            sub: 'u1',
            role: 'accountant',
            mandant_id: 'mandant-2',
          }),
          token_type: 'bearer',
        })
      }),
    )

    zeichne([MANDANT_A, MANDANT_B], MANDANT_A)
    fireEvent.click(screen.getByRole('button', { name: /mandant wechseln/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: /Mandant B/ }))
    })

    await waitFor(() => {
      expect(useAuthStore.getState().selectedMandant?.id).toBe('mandant-2')
    })
    expect(useAuthStore.getState().user?.mandant_id).toBe('mandant-2')
  })

  it('verwirft den Abfrage-Cache beim Wechsel', async () => {
    // Der wichtigste Test dieser Datei. Jede geladene Tabelle gehört zu genau einem
    // Mandanten. Bliebe eine Abfrage im Cache, deren Schlüssel die `mandant_id`
    // nicht enthält, würden nach dem Wechsel weiter die Zahlen des vorherigen
    // Mandanten angezeigt — und niemand würde es bemerken.
    server.use(
      http.post('/api/v1/auth/select-mandant', async () =>
        HttpResponse.json({
          access_token: createTestJwt({
            sub: 'u1',
            role: 'accountant',
            mandant_id: 'mandant-2',
          }),
          token_type: 'bearer',
        }),
      ),
    )

    const { qc } = zeichne([MANDANT_A, MANDANT_B], MANDANT_A)
    qc.setQueryData(['irgendwas-ohne-mandant-im-schluessel'], { betrag: 42 })
    expect(qc.getQueryData(['irgendwas-ohne-mandant-im-schluessel'])).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: /mandant wechseln/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: /Mandant B/ }))
    })

    await waitFor(() => {
      expect(qc.getQueryData(['irgendwas-ohne-mandant-im-schluessel'])).toBeUndefined()
    })
  })

  it('bleibt beim alten Mandanten, wenn der Wechsel abgelehnt wird', async () => {
    // Der Mandant kann inzwischen deaktiviert oder die Zuordnung entzogen worden
    // sein (Befund M9). Dann muss der bisherige Kontext erhalten bleiben — ein
    // halb gewechselter Zustand wäre schlimmer als keiner.
    server.use(
      http.post('/api/v1/auth/select-mandant', async () =>
        HttpResponse.json({ detail: 'Access to mandant denied' }, { status: 403 }),
      ),
    )

    zeichne([MANDANT_A, MANDANT_B], MANDANT_A)
    fireEvent.click(screen.getByRole('button', { name: /mandant wechseln/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: /Mandant B/ }))
    })

    expect(await screen.findByRole('alert')).toHaveTextContent(/nicht möglich/i)
    expect(useAuthStore.getState().selectedMandant?.id).toBe('mandant-1')
  })
})
