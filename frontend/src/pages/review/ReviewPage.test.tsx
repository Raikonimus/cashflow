/// <reference types="vitest" />
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { ReviewPage } from './ReviewPage'

const MANDANT_ID = 'mandant-1'

function setupUser() {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role: 'accountant', mandant_id: MANDANT_ID },
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
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
  })
})

const OPEN_ITEM = {
  id: 'item-1',
  mandant_id: MANDANT_ID,
  item_type: 'name_match_with_iban',
  journal_line_id: 'line-1',
  service_id: null,
  context: {
    partner_name_raw: 'Amazon EU',
    match_outcome: 'name_match',
    suggested_partner_name: 'Amazon',
    valuta_date: '2025-03-01',
    amount: '-99.99',
    reason: 'name_match',
  },
  status: 'open',
  created_at: '2025-03-01T00:00:00Z',
  updated_at: '2025-03-01T00:00:00Z',
  resolved_by: null,
  resolved_at: null,
  journal_line: {
    id: 'line-1',
    partner_id: 'partner-1',
    splits: [],
    valuta_date: '2025-03-01',
    booking_date: '2025-03-01',
    amount: '-99.99',
    currency: 'EUR',
    text: 'Prime Monatsgebühr',
    partner_name_raw: 'Amazon EU',
  },
  service: null,
  assigned_journal_lines: [],
}

const SERVICE_ASSIGNMENT_ITEM = {
  id: 'item-2',
  mandant_id: MANDANT_ID,
  item_type: 'service_assignment',
  journal_line_id: 'line-2',
  service_id: null,
  context: {
    current_service_id: 'service-base',
    current_service_name: 'Basisleistung',
    proposed_service_id: 'service-hosting',
    proposed_service_name: 'Hosting',
    reason: 'single_match',
  },
  status: 'open',
  created_at: '2025-03-01T00:00:00Z',
  updated_at: '2025-03-01T00:00:00Z',
  resolved_by: null,
  resolved_at: null,
  journal_line: {
    id: 'line-2',
    partner_id: 'partner-1',
    partner_name: 'Amazon EU',
    splits: [{ service_id: 'service-base', amount: '-49.00', assignment_mode: 'auto', amount_consistency_ok: false }],
    valuta_date: '2025-03-01',
    booking_date: '2025-03-01',
    amount: '-49.00',
    currency: 'EUR',
    text: 'Hosting April',
    partner_name_raw: 'Amazon EU',
  },
  service: null,
  assigned_journal_lines: [],
}

const SERVICE_TYPE_ITEM = {
  id: 'item-3',
  mandant_id: MANDANT_ID,
  item_type: 'service_type_review',
  journal_line_id: null,
  service_id: 'service-payroll',
  context: {
    previous_type: 'unknown',
    auto_assigned_type: 'employee',
    reason: 'keyword:lohn',
  },
  status: 'open',
  created_at: '2025-03-01T00:00:00Z',
  updated_at: '2025-03-01T00:00:00Z',
  resolved_by: null,
  resolved_at: null,
  journal_line: null,
  service: {
    id: 'service-payroll',
    partner_id: 'partner-2',
    name: 'Lohnlauf',
    service_type: 'employee',
    tax_rate: '0.00',
    valid_from: null,
    valid_to: null,
    service_type_manual: false,
    tax_rate_manual: false,
  },
  assigned_journal_lines: [
    {
      id: 'line-a',
      partner_id: 'partner-2',
      splits: [{ service_id: 'service-payroll', amount: '-1500.00', assignment_mode: 'auto', amount_consistency_ok: false }],
      valuta_date: '2025-03-31',
      booking_date: '2025-03-31',
      amount: '-1500.00',
      currency: 'EUR',
      text: 'Lohn März',
      partner_name_raw: 'Payroll GmbH',
    },
  ],
}

describe('ReviewPage', () => {
  it('shows empty state when no items', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [], total: 0, page: 1, size: 50, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() =>
      expect(screen.getByText(/queue ist leer/i)).toBeTruthy(),
    )
  })

  it('renders open review items', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [OPEN_ITEM], total: 1, page: 1, size: 100, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() =>
      expect(screen.getAllByText('Amazon EU').length).toBeGreaterThan(0),
    )
    expect(screen.getByText('Amazon')).toBeTruthy()
    expect(screen.getByText('Namens-Treffer')).toBeTruthy()
  })

  it('shows confirm button', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [OPEN_ITEM], total: 1, page: 1, size: 100, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => screen.getByText(/bestätigen/i))
    expect(screen.getByText(/bestätigen/i)).toBeTruthy()
  })

  it('calls confirm endpoint and refreshes list', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [OPEN_ITEM], total: 1, page: 1, size: 100, pages: 1 }),
      ),
      http.post(`/api/v1/mandants/${MANDANT_ID}/review/item-1/confirm`, () =>
        HttpResponse.json({ ...OPEN_ITEM, status: 'confirmed' }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => screen.getByText(/bestätigen/i))
    await act(async () => {
      fireEvent.click(screen.getByText(/^Bestätigen$/i))
    })
    // After confirm the list should be invalidated — no error
    await waitFor(() => screen.getByText(/bestätigen/i))
  })

  it('renders service assignment item and hides service_type_review card', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [SERVICE_ASSIGNMENT_ITEM, SERVICE_TYPE_ITEM], total: 2, page: 1, size: 100, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(screen.getByText(/leistungs-zuordnung/i)).toBeTruthy())
    expect(screen.getAllByText('Amazon EU').length).toBeGreaterThan(0)
    expect(screen.getByText('Basisleistung')).toBeTruthy()
    expect(screen.getByText('Hosting')).toBeTruthy()
    expect(screen.getByText(/vorschlag übernehmen/i)).toBeTruthy()
    // service_type_review items are now shown inline with direct actions (no redirect)
    expect(screen.getByText(/freigeben/i)).toBeTruthy()
    expect(screen.getByText(/typ korrigieren/i)).toBeTruthy()
  })

  it('filters items by tab', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [OPEN_ITEM, SERVICE_ASSIGNMENT_ITEM], total: 2, page: 1, size: 100, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    // both items visible in 'Alle' tab by default
    await waitFor(() => expect(screen.getAllByText('Amazon EU').length).toBeGreaterThan(0))
    expect(screen.getByText(/vorschlag übernehmen/i)).toBeTruthy()

    // switch to 'Leistung unklar' tab — only service_assignment should show
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /leistung unklar/i }))
    })
    await waitFor(() => expect(screen.getByText(/vorschlag übernehmen/i)).toBeTruthy())
    expect(screen.queryByText(/bestätigen\b(?!.*übernehmen)/i)).toBeNull()

    // switch to 'Kein Partner' tab — nothing matches
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /kein partner/i }))
    })
    await waitFor(() => expect(screen.getByText(/keine einträge/i)).toBeTruthy())
  })
})

const MANUAL_SERVICE_ITEM = {
  id: 'item-msa',
  mandant_id: MANDANT_ID,
  item_type: 'manual_service_assignment',
  journal_line_id: 'line-msa',
  service_id: null,
  context: {},
  status: 'open',
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-01T00:00:00Z',
  resolved_by: null,
  resolved_at: null,
  journal_line: {
    id: 'line-msa',
    partner_id: 'partner-msa',
    partner_name: 'Oesterreich Werbung',
    partner_name_raw: 'OEWT',
    splits: [{ service_id: 'service-base-msa', amount: '-150.00', assignment_mode: 'auto', amount_consistency_ok: false }],
    valuta_date: '2026-04-01',
    booking_date: '2026-04-01',
    amount: '-150.00',
    currency: 'EUR',
    text: 'Mitgliedsbeitrag April',
    partner_iban_raw: null,
  },
  service: null,
  assigned_journal_lines: [],
}

const PARTNER_MSA_SERVICES = [
  {
    id: 'service-base-msa',
    partner_id: 'partner-msa',
    name: 'Basisbeitrag',
    service_type: 'membership',
    tax_rate: '0.00',
    valid_from: null,
    valid_to: null,
    service_type_manual: false,
    tax_rate_manual: false,
    is_base_service: true,
  },
  {
    id: 'service-silver',
    partner_id: 'partner-msa',
    name: 'Silber-Mitgliedschaft',
    service_type: 'membership',
    tax_rate: '0.00',
    valid_from: null,
    valid_to: null,
    service_type_manual: false,
    tax_rate_manual: false,
    is_base_service: false,
  },
  {
    id: 'service-gold',
    partner_id: 'partner-msa',
    name: 'Gold-Mitgliedschaft',
    service_type: 'membership',
    tax_rate: '0.00',
    valid_from: null,
    valid_to: null,
    service_type_manual: false,
    tax_rate_manual: false,
    is_base_service: false,
  },
]

describe('ReviewPage – manual_service_assignment', () => {
  it('renders item with correct badge and partner name', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [MANUAL_SERVICE_ITEM], total: 1, page: 1, size: 100, pages: 1 }),
      ),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/partner-msa/services`, () =>
        HttpResponse.json(PARTNER_MSA_SERVICES),
      ),
    )
    await act(async () => { renderPage() })
    await waitFor(() => expect(screen.getByText('Manuelle Leistungszuordnung')).toBeTruthy())
    expect(screen.getAllByText('Oesterreich Werbung').length).toBeGreaterThan(0)
  })

  it('shows non-base services in inline grid and hides confirm/reject buttons', async () => {
    setupUser()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [MANUAL_SERVICE_ITEM], total: 1, page: 1, size: 100, pages: 1 }),
      ),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/partner-msa/services`, () =>
        HttpResponse.json(PARTNER_MSA_SERVICES),
      ),
    )
    await act(async () => { renderPage() })
    await waitFor(() => expect(screen.getByText('Silber-Mitgliedschaft')).toBeTruthy())
    expect(screen.getByText('Gold-Mitgliedschaft')).toBeTruthy()
    // Base service must NOT appear in the grid
    expect(screen.queryByText('Basisbeitrag')).toBeNull()
    // Confirm / Reject buttons must not appear
    expect(screen.queryByText(/^Bestätigen$/i)).toBeNull()
    expect(screen.queryByText(/^Ablehnen$/i)).toBeNull()
  })

  it('calls adjust endpoint with service_id when a service is clicked', async () => {
    setupUser()
    let adjustBody: unknown = null
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/review`, () =>
        HttpResponse.json({ items: [MANUAL_SERVICE_ITEM], total: 1, page: 1, size: 100, pages: 1 }),
      ),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/partner-msa/services`, () =>
        HttpResponse.json(PARTNER_MSA_SERVICES),
      ),
      http.post(`/api/v1/mandants/${MANDANT_ID}/review/item-msa/adjust`, async ({ request }) => {
        adjustBody = await request.json()
        return HttpResponse.json({ ...MANUAL_SERVICE_ITEM, status: 'adjusted' })
      }),
    )
    await act(async () => { renderPage() })
    await waitFor(() => expect(screen.getByText('Silber-Mitgliedschaft')).toBeTruthy())
    await act(async () => {
      fireEvent.click(screen.getByText('Silber-Mitgliedschaft'))
    })
    await waitFor(() => expect(adjustBody).toMatchObject({ service_id: 'service-silver' }))
  })
})
