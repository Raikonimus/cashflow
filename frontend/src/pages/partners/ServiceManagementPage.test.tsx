import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { ServiceManagementPage } from './ServiceManagementPage'

const MANDANT_ID = 'mandant-1'
const PARTNER_ID = 'partner-1'

const partnerDetail = {
  id: PARTNER_ID,
  mandant_id: MANDANT_ID,
  name: 'Amazon EU',
  display_name: null,
  is_active: true,
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
      user: { sub: 'u1', email: 'x@x.com', role, mandant_id: MANDANT_ID },
      selectedMandant: { id: MANDANT_ID, name: 'Test' },
      mandants: [],
    })
  })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/partners/${PARTNER_ID}/services`]}>
        <Routes>
          <Route path="/partners/:partnerId/services" element={<ServiceManagementPage />} />
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

describe('ServiceManagementPage', () => {
  it('creates, updates and deletes non-base services with revalidation notice', async () => {
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
        valid_from: '2026-01-01',
        valid_to: '2026-12-31',
        is_base_service: false,
        service_type_manual: false,
        tax_rate_manual: false,
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
        matchers: [
          {
            id: 'matcher-existing',
            pattern: 'hosting',
            pattern_type: 'string',
            created_at: '2026-04-01T00:00:00Z',
            updated_at: '2026-04-01T00:00:00Z',
          },
        ],
      },
    ]

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json(services)),
      http.post(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string | null>
        services.push({
          id: 'service-support',
          partner_id: PARTNER_ID,
          name: String(body.name),
          description: body.description ? String(body.description) : null,
          service_type: String(body.service_type ?? 'unknown'),
          tax_rate: String(body.tax_rate ?? '20.00'),
          valid_from: body.valid_from ? String(body.valid_from) : null,
          valid_to: body.valid_to ? String(body.valid_to) : null,
          is_base_service: false,
          service_type_manual: false,
          tax_rate_manual: false,
          created_at: '2026-04-02T00:00:00Z',
          updated_at: '2026-04-02T00:00:00Z',
          matchers: [],
        })
        return HttpResponse.json(services[services.length - 1], { status: 201 })
      }),
      http.patch(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string | null>
        services[1] = {
          ...services[1],
          name: String(body.name),
          description: body.description ? String(body.description) : null,
          service_type: String(body.service_type ?? services[1].service_type),
          tax_rate: String(body.tax_rate ?? services[1].tax_rate),
          valid_from: body.valid_from ? String(body.valid_from) : null,
          valid_to: body.valid_to ? String(body.valid_to) : null,
        }
        return HttpResponse.json(services[1])
      }),
      http.delete(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting`, () => {
        services.splice(1, 1)
        return new HttpResponse(null, { status: 204 })
      }),
      http.post(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting/matchers`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string>
        services[1].matchers.push({
          id: 'matcher-new',
          pattern: body.pattern,
          pattern_type: body.pattern_type as 'string' | 'regex',
          created_at: '2026-04-02T00:00:00Z',
          updated_at: '2026-04-02T00:00:00Z',
        })
        return HttpResponse.json(services[1].matchers[services[1].matchers.length - 1], { status: 201 })
      }),
      http.patch(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting/matchers/matcher-existing`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string>
        services[1].matchers[0] = {
          ...services[1].matchers[0],
          pattern: body.pattern,
          pattern_type: body.pattern_type as 'string' | 'regex',
        }
        return HttpResponse.json(services[1].matchers[0])
      }),
      http.delete(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting/matchers/matcher-existing`, () => {
        services[1].matchers = services[1].matchers.filter((matcher) => matcher.id !== 'matcher-existing')
        return new HttpResponse(null, { status: 204 })
      }),
    )

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getAllByText('Basisleistung')[0]).toBeInTheDocument())
    expect(screen.getByText(/ohne datumsangaben ist die leistung immer gültig/i)).toBeInTheDocument()
    expect(screen.getByText(/leer gelassene datumsfelder bedeuten: immer gültig/i)).toBeInTheDocument()
    expect(screen.getByText(/Zeitraum: 2026-01-01 bis 2026-12-31/)).toBeInTheDocument()

    fireEvent.change(screen.getAllByPlaceholderText(/z\. b\./i)[0], { target: { value: 'Support' } })
    fireEvent.change(screen.getByPlaceholderText(/optional/i), { target: { value: 'Premium Support' } })
    fireEvent.change(screen.getAllByDisplayValue('Unbekannt')[0], { target: { value: 'shareholder' } })
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-05-01' } })
    fireEvent.change(screen.getByLabelText('Gültig bis'), { target: { value: '2026-10-31' } })
    fireEvent.click(screen.getByRole('button', { name: /leistung anlegen/i }))

    await waitFor(() => expect(screen.getByText('Support')).toBeInTheDocument())
    expect(screen.getByText(/Typ: Gesellschafter/)).toBeInTheDocument()
    expect(screen.getByText(/Leistung gespeichert/)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /bearbeiten/i })[1])
    fireEvent.change(screen.getByDisplayValue('Hosting'), { target: { value: 'Cloud Hosting' } })
    fireEvent.click(screen.getByRole('button', { name: /änderungen speichern/i }))

    await waitFor(() => expect(screen.getByText('Cloud Hosting')).toBeInTheDocument())
    expect(screen.getByText(/Leistung aktualisiert/)).toBeInTheDocument()

    fireEvent.change(screen.getAllByPlaceholderText(/z\. b\. hosting oder \^aws/i)[0], { target: { value: '^AWS' } })
    fireEvent.change(screen.getAllByDisplayValue('String')[0], { target: { value: 'regex' } })
    fireEvent.click(screen.getAllByRole('button', { name: /matcher anlegen/i })[0])

    await waitFor(() => expect(screen.getByText('^AWS')).toBeInTheDocument())
    expect(screen.getByText(/Matcher gespeichert/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Matcher hosting bearbeiten' }))
    fireEvent.change(screen.getByDisplayValue('hosting'), { target: { value: 'aws hosting' } })
    fireEvent.click(screen.getByRole('button', { name: /matcher speichern/i }))

    await waitFor(() => expect(screen.getByText('aws hosting')).toBeInTheDocument())
    expect(screen.getByText(/Matcher aktualisiert/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Matcher aws hosting löschen' }))

    await waitFor(() => expect(screen.queryByText('aws hosting')).not.toBeInTheDocument())
    expect(screen.getByText(/Matcher gelöscht/)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /löschen/i })[1])

    await waitFor(() => expect(screen.queryByText('Cloud Hosting')).not.toBeInTheDocument())
    expect(screen.getByText(/Leistung gelöscht/)).toBeInTheDocument()

    confirmSpy.mockRestore()
  })

  it('keeps base service protected in the ui', async () => {
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
    ]

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json(services)),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getAllByText('Basisleistung')[0]).toBeInTheDocument())
    expect(screen.getByText(/Die Basisleistung bleibt erhalten/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /löschen/i })).toBeDisabled()
    expect(screen.getByText(/Für die Basisleistung sind keine Matcher erlaubt/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /bearbeiten/i }))
    expect(screen.getByDisplayValue('Basisleistung')).toBeDisabled()
  })

  it('shows regex validation errors inline for matcher forms', async () => {
    setup()

    const services = [
      {
        id: 'service-hosting',
        partner_id: PARTNER_ID,
        name: 'Hosting',
        description: 'Managed Kubernetes',
        service_type: 'supplier',
        tax_rate: '10.00',
        valid_from: '2026-01-01',
        valid_to: '2026-12-31',
        is_base_service: false,
        service_type_manual: false,
        tax_rate_manual: false,
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
        matchers: [],
      },
    ]

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json(services)),
      http.post(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting/matchers`, () =>
        HttpResponse.json({ detail: 'Invalid regex pattern: missing ), unterminated subpattern at position 0' }, { status: 422 }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Hosting')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText(/z\. b\. hosting oder \^aws/i), { target: { value: '(' } })
    fireEvent.change(screen.getByDisplayValue('String'), { target: { value: 'regex' } })
    fireEvent.click(screen.getByRole('button', { name: /matcher anlegen/i }))

    await waitFor(() => expect(screen.getByText(/Invalid regex pattern/)).toBeInTheDocument())
  })

  it('allows clearing service validity dates back to always valid', async () => {
    setup()

    const services = [
      {
        id: 'service-hosting',
        partner_id: PARTNER_ID,
        name: 'Hosting',
        description: 'Managed Kubernetes',
        service_type: 'supplier',
        tax_rate: '10.00',
        valid_from: '2026-01-01',
        valid_to: '2026-12-31',
        is_base_service: false,
        service_type_manual: false,
        tax_rate_manual: false,
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
        matchers: [],
      },
    ]

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}`, () => HttpResponse.json(partnerDetail)),
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners/${PARTNER_ID}/services`, () => HttpResponse.json(services)),
      http.patch(`/api/v1/mandants/${MANDANT_ID}/services/service-hosting`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string | null>
        expect(body.valid_from).toBeNull()
        expect(body.valid_to).toBeNull()
        services[0] = {
          ...services[0],
          valid_from: null,
          valid_to: null,
        }
        return HttpResponse.json(services[0])
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Hosting')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /bearbeiten/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /auf immer gültig zurücksetzen/i })[1])
    fireEvent.click(screen.getByRole('button', { name: /änderungen speichern/i }))

    await waitFor(() => expect(screen.getByText(/Zeitraum: Immer gültig/i)).toBeInTheDocument())
  })
})