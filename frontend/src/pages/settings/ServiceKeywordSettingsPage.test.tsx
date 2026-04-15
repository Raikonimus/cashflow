import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { ServiceKeywordSettingsPage } from './ServiceKeywordSettingsPage'

const MANDANT_ID = 'mandant-1'

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
      <MemoryRouter initialEntries={['/settings/service-keywords']}>
        <Routes>
          <Route path="/settings/service-keywords" element={<ServiceKeywordSettingsPage />} />
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

describe('ServiceKeywordSettingsPage', () => {
  it('groups, creates, updates and deletes keyword rules', async () => {
    setup()

    const keywords = [
      {
        id: 'kw-1',
        mandant_id: MANDANT_ID,
        pattern: 'Gehalt',
        pattern_type: 'string',
        target_service_type: 'employee',
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
      },
      {
        id: 'kw-2',
        mandant_id: MANDANT_ID,
        pattern: '^Finanzamt',
        pattern_type: 'regex',
        target_service_type: 'authority',
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
      },
      {
        id: 'kw-3',
        mandant_id: MANDANT_ID,
        pattern: 'Privatentnahme',
        pattern_type: 'string',
        target_service_type: 'shareholder',
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
      },
    ]

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/settings/service-keywords`, () =>
        HttpResponse.json({
          items: keywords,
          system_defaults: [
            { pattern: 'lohn', pattern_type: 'string', target_service_type: 'employee' },
            { pattern: 'entnahme', pattern_type: 'string', target_service_type: 'shareholder' },
            { pattern: 'steuer', pattern_type: 'string', target_service_type: 'authority' },
          ],
        }),
      ),
      http.post(`/api/v1/mandants/${MANDANT_ID}/settings/service-keywords`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string>
        keywords.push({
          id: 'kw-4',
          mandant_id: MANDANT_ID,
          pattern: body.pattern,
          pattern_type: body.pattern_type as 'string' | 'regex',
          target_service_type: body.target_service_type as 'employee' | 'shareholder' | 'authority',
          created_at: '2026-04-02T00:00:00Z',
          updated_at: '2026-04-02T00:00:00Z',
        })
        return HttpResponse.json(keywords.at(-1), { status: 201 })
      }),
      http.patch(`/api/v1/mandants/${MANDANT_ID}/settings/service-keywords/kw-1`, async ({ request }) => {
        const body = (await request.json()) as Record<string, string>
        keywords[0] = {
          ...keywords[0],
          pattern: body.pattern,
          pattern_type: body.pattern_type as 'string' | 'regex',
          target_service_type: body.target_service_type as 'employee' | 'shareholder' | 'authority',
        }
        return HttpResponse.json(keywords[0])
      }),
      http.delete(`/api/v1/mandants/${MANDANT_ID}/settings/service-keywords/kw-1`, () => {
        keywords.splice(0, 1)
        return new HttpResponse(null, { status: 204 })
      }),
    )

    const confirmSpy = vi.spyOn(globalThis, 'confirm').mockReturnValue(true)

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Mitarbeiter' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Gesellschafter' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Behörde' })).toBeInTheDocument()
    expect(screen.getByText('Gehalt')).toBeInTheDocument()
    expect(screen.getByText('Privatentnahme')).toBeInTheDocument()
    expect(screen.getByText('^Finanzamt')).toBeInTheDocument()
    expect(screen.getByText('lohn · String')).toBeInTheDocument()
    expect(screen.getByText('entnahme · String')).toBeInTheDocument()
    expect(screen.getByText('steuer · String')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Pattern'), { target: { value: 'Lohnnebenkosten' } })
    fireEvent.click(screen.getByRole('button', { name: /regel anlegen/i }))

    await waitFor(() => expect(screen.getByText('Lohnnebenkosten')).toBeInTheDocument())
    expect(screen.getByText(/Keyword-Regel gespeichert/)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /bearbeiten/i })[0])
    fireEvent.change(screen.getByDisplayValue('Gehalt'), { target: { value: 'Gehalt AT' } })
    fireEvent.click(screen.getByRole('button', { name: /regel speichern/i }))

    await waitFor(() => expect(screen.getByText('Gehalt AT')).toBeInTheDocument())
    expect(screen.getByText(/Keyword-Regel aktualisiert/)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /löschen/i })[0])

    await waitFor(() => expect(screen.queryByText('Gehalt AT')).not.toBeInTheDocument())
    expect(screen.getByText(/Keyword-Regel gelöscht/)).toBeInTheDocument()

    confirmSpy.mockRestore()
  })

  it('blocks invalid regex and shows inline validation', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/settings/service-keywords`, () =>
        HttpResponse.json({ items: [], system_defaults: [] }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Service-Keywords')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Pattern'), { target: { value: '(' } })
    fireEvent.change(screen.getByLabelText('Typ'), { target: { value: 'regex' } })

    expect(screen.getByText(/Ungültige Regex/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /regel anlegen/i })).toBeDisabled()
  })
})