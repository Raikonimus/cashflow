import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'

import { TestingPage } from './TestingPage'

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
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/settings/testing']}>
        <Routes>
          <Route path="/settings/testing" element={<TestingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
  })
})

describe('TestingPage', () => {
  it('runs the service amount consistency test and shows inconsistent services with ignored lines highlighted', async () => {
    setup()

    server.use(
      http.post(`/api/v1/mandants/${MANDANT_ID}/settings/tests/service-amount-consistency`, () =>
        HttpResponse.json({
          total_checked_services: 3,
          inconsistent_services: [
            {
              service_id: 'service-1',
              service_name: 'Hosting',
              partner_id: 'partner-1',
              partner_name: 'Alpha GmbH',
              positive_line_count: 1,
              negative_line_count: 1,
              lines: [
                {
                  id: 'line-1',
                  account_id: 'account-1',
                  import_run_id: 'run-1',
                  partner_id: 'partner-1',
                  service_id: 'service-1',
                  service_assignment_mode: 'manual',
                  service_amount_consistency_ok: false,
                  valuta_date: '2026-02-02',
                  booking_date: '2026-02-02',
                  amount: '25.00',
                  currency: 'EUR',
                  text: 'Gutschrift Hosting',
                  partner_name_raw: 'Alpha GmbH',
                  partner_iban_raw: null,
                  partner_account_raw: '12345',
                  partner_blz_raw: '20111',
                  partner_bic_raw: null,
                  unmapped_data: null,
                  created_at: '2026-02-02T00:00:00Z',
                },
                {
                  id: 'line-2',
                  account_id: 'account-1',
                  import_run_id: 'run-1',
                  partner_id: 'partner-1',
                  service_id: 'service-1',
                  service_assignment_mode: 'manual',
                  service_amount_consistency_ok: false,
                  valuta_date: '2026-02-01',
                  booking_date: '2026-02-01',
                  amount: '-50.00',
                  currency: 'EUR',
                  text: 'Rechnung Hosting',
                  partner_name_raw: 'Alpha GmbH',
                  partner_iban_raw: null,
                  partner_account_raw: '12345',
                  partner_blz_raw: '20111',
                  partner_bic_raw: null,
                  unmapped_data: null,
                  created_at: '2026-02-01T00:00:00Z',
                },
                {
                  id: 'line-3',
                  account_id: 'account-1',
                  import_run_id: 'run-1',
                  partner_id: 'partner-1',
                  service_id: 'service-1',
                  service_assignment_mode: 'manual',
                  service_amount_consistency_ok: true,
                  valuta_date: '2026-01-30',
                  booking_date: '2026-01-30',
                  amount: '-10.00',
                  currency: 'EUR',
                  text: 'Kulanz Hosting',
                  partner_name_raw: 'Alpha GmbH',
                  partner_iban_raw: null,
                  partner_account_raw: '12345',
                  partner_blz_raw: '20111',
                  partner_bic_raw: null,
                  unmapped_data: null,
                  created_at: '2026-01-30T00:00:00Z',
                },
              ],
            },
          ],
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    fireEvent.click(screen.getByRole('button', { name: /Test 2: Service-Betragskonsistenz/i }))
    fireEvent.click(screen.getByRole('button', { name: /Test 2 ausführen/i }))

    await waitFor(() => expect(screen.getByText(/Geprüfte Services:/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /Zur Servicekonfiguration/i })).toHaveAttribute('href', '/settings/service-keywords')
    const serviceCardTitle = screen.getByText('Alpha GmbH / Hosting')
    expect(serviceCardTitle).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Partner öffnen/i })).toHaveAttribute('href', '/partners/partner-1')
    expect(screen.getByText(/Eingänge: 1/)).toBeInTheDocument()
    expect(serviceCardTitle.closest('article')).toHaveTextContent('Ausgänge: 1')
    expect(screen.getByText(/1 Buchung ist als in Ordnung markiert und wird im Test ignoriert./i)).toBeInTheDocument()

    const details = screen.getByText(/Buchungszeilen anzeigen \(3\)/i).closest('details')
    expect(details).not.toBeNull()
    expect(details).not.toHaveAttribute('open')

    fireEvent.click(screen.getByText(/Buchungszeilen anzeigen \(3\)/i))

    expect(details).toHaveAttribute('open')

    expect(screen.getByText('Gutschrift Hosting')).toBeInTheDocument()
    expect(screen.getByText('Rechnung Hosting')).toBeInTheDocument()
    expect(screen.getByText('Kulanz Hosting')).toBeInTheDocument()
    expect(screen.getByText(/Ist in Ordnung/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Markierung entfernen/i })).toBeInTheDocument()
  })

  it('marks a service amount consistency line as ok and reloads the result', async () => {
    setup()

    let isMarkedOk = false

    server.use(
      http.post(`/api/v1/mandants/${MANDANT_ID}/settings/tests/service-amount-consistency`, () =>
        HttpResponse.json({
          total_checked_services: 1,
          inconsistent_services: isMarkedOk
            ? []
            : [
                {
                  service_id: 'service-1',
                  service_name: 'Hosting',
                  partner_id: 'partner-1',
                  partner_name: 'Alpha GmbH',
                  positive_line_count: 1,
                  negative_line_count: 1,
                  lines: [
                    {
                      id: 'line-1',
                      account_id: 'account-1',
                      import_run_id: 'run-1',
                      partner_id: 'partner-1',
                      service_id: 'service-1',
                      service_assignment_mode: 'manual',
                      service_amount_consistency_ok: false,
                      valuta_date: '2026-02-02',
                      booking_date: '2026-02-02',
                      amount: '25.00',
                      currency: 'EUR',
                      text: 'Gutschrift Hosting',
                      partner_name_raw: 'Alpha GmbH',
                      partner_iban_raw: null,
                      partner_account_raw: '12345',
                      partner_blz_raw: '20111',
                      partner_bic_raw: null,
                      unmapped_data: null,
                      created_at: '2026-02-02T00:00:00Z',
                    },
                    {
                      id: 'line-2',
                      account_id: 'account-1',
                      import_run_id: 'run-1',
                      partner_id: 'partner-1',
                      service_id: 'service-1',
                      service_assignment_mode: 'manual',
                      service_amount_consistency_ok: false,
                      valuta_date: '2026-02-01',
                      booking_date: '2026-02-01',
                      amount: '-50.00',
                      currency: 'EUR',
                      text: 'Rechnung Hosting',
                      partner_name_raw: 'Alpha GmbH',
                      partner_iban_raw: null,
                      partner_account_raw: '12345',
                      partner_blz_raw: '20111',
                      partner_bic_raw: null,
                      unmapped_data: null,
                      created_at: '2026-02-01T00:00:00Z',
                    },
                  ],
                },
              ],
        }),
      ),
      http.post(`/api/v1/mandants/${MANDANT_ID}/settings/tests/service-amount-consistency/lines/line-1/ok`, async ({ request }) => {
        const body = await request.json() as { is_ok?: boolean }
        isMarkedOk = body.is_ok === true
        return HttpResponse.json({
          journal_line_id: 'line-1',
          service_amount_consistency_ok: isMarkedOk,
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    fireEvent.click(screen.getByRole('button', { name: /Test 2: Service-Betragskonsistenz/i }))
    fireEvent.click(screen.getByRole('button', { name: /Test 2 ausführen/i }))

    await waitFor(() => expect(screen.getByText('Alpha GmbH / Hosting')).toBeInTheDocument())

    fireEvent.click(screen.getByText(/Buchungszeilen anzeigen \(2\)/i))
    fireEvent.click(screen.getAllByRole('button', { name: /Als in Ordnung markieren/i })[0])

    await waitFor(() => {
      expect(screen.getByText(/Keine Services mit gemischten Eingangs- und Ausgangsbuchungen gefunden./i)).toBeInTheDocument()
    })
  })
})