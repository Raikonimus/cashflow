import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { JournalPage } from './JournalPage'

const MANDANT_ID = 'mandant-1'

function setup(role = 'accountant') {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role, mandant_id: MANDANT_ID },
      selectedMandant: { id: MANDANT_ID, name: 'Test' },
      mandants: [],
    })
  })
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JournalPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
  })
})

describe('JournalPage', () => {
  it('shows service names as a dedicated column', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () =>
        HttpResponse.json({
          items: [
            {
              id: 'line-1',
              account_id: 'account-1',
              import_run_id: 'run-1',
              partner_id: 'partner-1',
              partner_name: 'Amazon EU',
              service_id: 'service-1',
              service_name: 'Hosting',
              service_assignment_mode: 'manual',
              valuta_date: '2026-04-01',
              booking_date: '2026-04-01',
              amount: '-49.00',
              currency: 'EUR',
              text: 'Hosting April',
              partner_name_raw: 'Amazon EU',
              partner_iban_raw: null,
              partner_account_raw: null,
              partner_blz_raw: null,
              partner_bic_raw: null,
              unmapped_data: null,
              created_at: '2026-04-01T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          size: 50,
          pages: 1,
        }),
      ),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2026] })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/accounts`, () => HttpResponse.json([])),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Leistung')).toBeInTheDocument())
    expect(screen.getByText('Hosting')).toBeInTheDocument()
  })

  it('renders nested unmapped_data safely in the info tooltip', async () => {
    setup()

    const { container } = renderPage()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () =>
        HttpResponse.json({
          items: [
            {
              id: 'line-1',
              account_id: 'account-1',
              import_run_id: 'run-1',
              partner_id: 'partner-1',
              partner_name: 'SIPGATE',
              service_id: null,
              service_name: null,
              service_assignment_mode: null,
              valuta_date: '2026-03-20',
              booking_date: '2026-03-20',
              amount: '-20.00',
              currency: 'EUR',
              text: 'E-COMM 20,00 DE K2 19.03. 14:09 SIPGATE',
              partner_name_raw: 'SIPGATE',
              partner_iban_raw: null,
              partner_account_raw: '40100101600',
              partner_blz_raw: '20111',
              partner_bic_raw: null,
              unmapped_data: {
                Buchungsreferenz: '201002603202AEI-08EZD2000898',
                _cashflow_source_values: {
                  Buchungsreferenz: '201002603202AEI-08EZD2000898',
                  Betrag: '20,00',
                },
              },
              created_at: '2026-04-01T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          size: 50,
          pages: 1,
        }),
      ),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2026] })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/accounts`, () => HttpResponse.json([])),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('E-COMM 20,00 DE K2 19.03. 14:09 SIPGATE')).toBeInTheDocument())

    const infoButton = container.querySelector('button svg')?.parentElement as HTMLButtonElement
    expect(infoButton).not.toBeNull()

    fireEvent.mouseEnter(infoButton.parentElement)

    await waitFor(() => expect(screen.getByText('Buchungsreferenz')).toBeInTheDocument())
    expect(screen.queryByText(/_cashflow_source_values/)).not.toBeInTheDocument()
    expect(screen.getByText('201002603202AEI-08EZD2000898')).toBeInTheDocument()
  })
})