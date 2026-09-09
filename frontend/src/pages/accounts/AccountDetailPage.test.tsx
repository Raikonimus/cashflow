import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { AccountDetailPage } from './AccountDetailPage'

const MANDANT_ID = 'mandant-1'
const ACCOUNT_ID = 'acc-1'

function account(openingBalance: string) {
  return {
    id: ACCOUNT_ID,
    mandant_id: MANDANT_ID,
    name: 'Girokonto',
    iban: null,
    currency: 'EUR',
    opening_balance: openingBalance,
    is_active: true,
    has_column_mapping: false,
    created_at: '2025-01-01T00:00:00Z',
  }
}

function setup(openingBalance = '0.00') {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role: 'accountant', mandant_id: MANDANT_ID },
      selectedMandant: { id: MANDANT_ID, name: 'Test' },
      mandants: [],
    })
  })
  server.use(
    http.get(`/api/v1/mandants/${MANDANT_ID}/accounts`, () =>
      HttpResponse.json([account(openingBalance)]),
    ),
    http.get(`/api/v1/mandants/${MANDANT_ID}/accounts/${ACCOUNT_ID}/column-mapping`, () =>
      HttpResponse.json({ detail: 'not found' }, { status: 404 }),
    ),
    http.get(`/api/v1/mandants/${MANDANT_ID}/accounts/${ACCOUNT_ID}/excluded-identifiers`, () =>
      HttpResponse.json([]),
    ),
  )
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/accounts/${ACCOUNT_ID}`]}>
        <Routes>
          <Route path="/accounts/:accountId" element={<AccountDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Die Seite enthält mehrere Formulare — hier interessiert nur das Startsaldo-Formular. */
async function openingBalanceForm() {
  const input = await screen.findByLabelText('Betrag in EUR')
  const form = input.closest('form')
  if (!form) throw new Error('Startsaldo-Formular nicht gefunden')
  return { input, saveButton: within(form).getByRole('button', { name: 'Speichern' }) }
}

describe('AccountDetailPage – Startsaldo', () => {
  it('zeigt den gespeicherten Startsaldo', async () => {
    setup('1500.00')
    renderPage()

    const input = await screen.findByLabelText('Betrag in EUR')
    expect(input).toHaveValue('1500,00')
  })

  it('speichert einen geänderten Startsaldo normalisiert', async () => {
    setup('0.00')
    let patched: Record<string, unknown> | null = null
    server.use(
      http.patch(`/api/v1/mandants/${MANDANT_ID}/accounts/${ACCOUNT_ID}`, async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(account('1234.56'))
      }),
    )
    renderPage()

    const { input, saveButton } = await openingBalanceForm()
    await userEvent.clear(input)
    await userEvent.type(input, '1.234,56')
    await userEvent.click(saveButton)

    await waitFor(() => expect(patched).toEqual({ opening_balance: '1234.56' }))
    expect(await screen.findByText('Gespeichert.')).toBeInTheDocument()
  })

  it('lehnt eine ungültige Eingabe ab, ohne zu speichern', async () => {
    setup('0.00')
    let patchCalled = false
    server.use(
      http.patch(`/api/v1/mandants/${MANDANT_ID}/accounts/${ACCOUNT_ID}`, () => {
        patchCalled = true
        return HttpResponse.json(account('0.00'))
      }),
    )
    renderPage()

    const { input, saveButton } = await openingBalanceForm()
    await userEvent.clear(input)
    await userEvent.type(input, 'keine Zahl')
    await userEvent.click(saveButton)

    expect(await screen.findByText(/Bitte einen Betrag eingeben/)).toBeInTheDocument()
    expect(patchCalled).toBe(false)
  })
})
