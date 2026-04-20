import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import type { PartnerDetail } from '@/api/partners'
import { PartnerDetailPage } from './PartnerDetailPage'

const MANDANT_ID = 'mandant-1'
const PARTNER_ID = 'partner-1'

const partnerDetail = {
  id: PARTNER_ID,
  mandant_id: MANDANT_ID,
  name: 'Amazon EU',
  display_name: null,
  is_active: true,
  manual_assignment: false,
  ibans: [],
  accounts: [],
  names: [],
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-01T00:00:00Z',
}

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

  class MockIntersectionObserver {
    observe() {}
    disconnect() {}
    unobserve() {}
  }

  Object.defineProperty(window, 'IntersectionObserver', {
    writable: true,
    configurable: true,
    value: MockIntersectionObserver,
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/partners/${PARTNER_ID}`]}>
        <Routes>
          <Route path="/partners/:partnerId" element={<PartnerDetailPage />} />
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

describe('PartnerDetailPage', () => {
  it('allows adding and removing further account numbers', async () => {
    setup()

    let currentPartner: PartnerDetail = {
      ...partnerDetail,
      accounts: [
        {
          id: 'account-1',
          account_number: '1234567',
          blz: '10020030',
          bic: 'BANKDEFFXXX',
          created_at: '2026-04-01T00:00:00Z',
        },
      ],
    }

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(currentPartner)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/neighbors`, () => HttpResponse.json({ prev: null, next: null })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json([])),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () => HttpResponse.json({ items: [], total: 0, page: 1, size: 25, pages: 1 })),
      http.post(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/accounts/preview`, () =>
        HttpResponse.json({ matched_lines: [], total: 0 }),
      ),
      http.post(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/accounts`, async ({ request }) => {
        const body = await request.json() as { account_number: string; blz?: string; bic?: string }
        const created = {
          id: 'account-2',
          account_number: body.account_number,
          blz: body.blz ?? null,
          bic: body.bic ?? null,
          created_at: '2026-04-02T00:00:00Z',
        }
        currentPartner = {
          ...currentPartner,
          accounts: [...currentPartner.accounts, created],
        }
        return HttpResponse.json(created, { status: 201 })
      }),
      http.delete(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/accounts/account-1`, () => {
        currentPartner = {
          ...currentPartner,
          accounts: currentPartner.accounts.filter((account) => account.id !== 'account-1'),
        }
        return new HttpResponse(null, { status: 204 })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('1234567')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Kontonummer'), { target: { value: '7654321' } })
    fireEvent.change(screen.getByLabelText('BLZ'), { target: { value: '20030040' } })
    fireEvent.change(screen.getByLabelText('BIC'), { target: { value: 'GENODEF1XXX' } })
    fireEvent.click(screen.getAllByRole('button', { name: /testen/i })[1])
    await waitFor(() => expect(screen.getAllByRole('button', { name: /hinzufügen/i })[1]).toBeEnabled())
    fireEvent.click(screen.getAllByRole('button', { name: /hinzufügen/i })[1])

    await waitFor(() => expect(screen.getByText('7654321')).toBeInTheDocument())
    expect(screen.getByText(/BLZ 20030040/)).toBeInTheDocument()
    expect(screen.getByText('GENODEF1XXX')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /entfernen/i })[0])

    await waitFor(() => expect(screen.queryByText('1234567')).not.toBeInTheDocument())
  })

  it('shows service summary and links to the dedicated service management page', async () => {
    setup()

    const services = [
      {
        id: 'service-base',
        partner_id: PARTNER_ID,
        name: 'Basisleistung',
        description: null,
        service_type: 'unknown',
        tax_rate: '20.00',
        valid_from: null,
        valid_to: null,
        is_base_service: true,
        service_type_manual: false,
        tax_rate_manual: false,
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
        matchers: [],
      },
      {
        id: 'service-hosting',
        partner_id: PARTNER_ID,
        name: 'Hosting',
        description: 'Managed Kubernetes',
        service_type: 'supplier',
        tax_rate: '10.00',
        valid_from: null,
        valid_to: null,
        is_base_service: false,
        service_type_manual: false,
        tax_rate_manual: false,
        created_at: '2026-04-02T00:00:00Z',
        updated_at: '2026-04-02T00:00:00Z',
        matchers: [{
          id: 'matcher-1',
          pattern: 'hosting',
          pattern_type: 'string',
          created_at: '2026-04-02T00:00:00Z',
          updated_at: '2026-04-02T00:00:00Z',
        }],
      },
    ]

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/neighbors`, () => HttpResponse.json({ prev: null, next: null })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json(services)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () => HttpResponse.json({ items: [], total: 0, page: 1, size: 25, pages: 1 })),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getAllByText('Basisleistung')[0]).toBeInTheDocument())

    expect(screen.getByText('Hosting')).toBeInTheDocument()
    expect(screen.getByText('Managed Kubernetes')).toBeInTheDocument()
    expect(screen.getByText(/Typ: Lieferant/)).toBeInTheDocument()
    expect(screen.getByText(/Steuer: 10.00%/)).toBeInTheDocument()
    expect(screen.getByText(/Matcher: 1/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /leistungen verwalten/i })).toHaveAttribute('href', `/partners/${PARTNER_ID}/services`)
  })

  it('shows a warning when deleting a partner with bookings is blocked', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/neighbors`, () => HttpResponse.json({ prev: null, next: null })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json([])),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () => HttpResponse.json({ items: [], total: 0, page: 1, size: 25, pages: 1 })),
      http.delete(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () =>
        HttpResponse.json(
          { detail: 'Partner has journal entries. Move the bookings first before deleting this partner.' },
          { status: 409 },
        ),
      ),
    )

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByRole('button', { name: /partner löschen/i })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /partner löschen/i }))

    await waitFor(() => expect(screen.getByText(/verschiebe zuerst alle buchungen auf einen anderen partner/i)).toBeInTheDocument())

    confirmSpy.mockRestore()
  })

  it('shows service names as a column in the partner journal table', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/neighbors`, () => HttpResponse.json({ prev: null, next: null })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json([])),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () =>
        HttpResponse.json({
          items: [
            {
              id: 'line-1',
              account_id: 'account-1',
              import_run_id: 'run-1',
              partner_id: PARTNER_ID,
              partner_name: 'Amazon EU',
              service_id: 'service-1',
              service_name: 'Hosting',
              splits: [{ service_id: 'service-1', service_name: 'Hosting', amount: '-49.00', assignment_mode: 'manual', amount_consistency_ok: false }],
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
          size: 25,
          pages: 1,
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByRole('columnheader', { name: /leistung/i })).toBeInTheDocument())
    expect(screen.getByText('Hosting')).toBeInTheDocument()
  })

  it('shows the manual assignment checkbox and toggles it', async () => {
    setup()
    const user = userEvent.setup()
    let currentPartner = { ...partnerDetail, manual_assignment: false }

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(currentPartner)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/neighbors`, () => HttpResponse.json({ prev: null, next: null })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json([])),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () => HttpResponse.json({ items: [], total: 0, page: 1, size: 25, pages: 1 })),
      http.patch(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        currentPartner = { ...currentPartner, ...body }
        return HttpResponse.json(currentPartner)
      }),
    )

    await act(async () => { renderPage() })

    const checkbox = await screen.findByRole('checkbox', { name: /manuelle zuordnung/i })
    expect(checkbox).not.toBeChecked()

    await user.click(checkbox)

    await waitFor(() => {
      expect(currentPartner.manual_assignment).toBe(true)
      expect(screen.getByRole('checkbox', { name: /manuelle zuordnung/i })).toBeChecked()
    })
  })

  it('does not show the manual assignment checkbox for viewers', async () => {
    setup('viewer')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/neighbors`, () => HttpResponse.json({ prev: null, next: null })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json([])),
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal`, () => HttpResponse.json({ items: [], total: 0, page: 1, size: 25, pages: 1 })),
    )

    await act(async () => { renderPage() })

    await waitFor(() => expect(screen.getByText('Amazon EU')).toBeInTheDocument())
    expect(screen.queryByRole('checkbox', { name: /manuelle zuordnung/i })).not.toBeInTheDocument()
  })
})