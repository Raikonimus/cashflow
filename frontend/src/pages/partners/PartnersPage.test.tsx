import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { PartnersPage } from './PartnersPage'

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
        <PartnersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
  })
})

const PARTNERS = [
  {
    id: 'p1',
    name: 'Amazon EU',
    is_active: true,
    manual_assignment: false,
    service_types: ['supplier', 'supplier', 'unknown'],
    iban_count: 2,
    name_count: 1,
    journal_line_count: 5,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'p2',
    name: 'Alter Partner',
    is_active: false,
    manual_assignment: false,
    service_types: ['employee', 'shareholder'],
    iban_count: 0,
    name_count: 0,
    journal_line_count: 0,
    created_at: '2025-01-01T00:00:00Z',
  },
]

describe('PartnersPage', () => {
  it('renders partner list', async () => {
    setup()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, () =>
        HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(screen.getByText('Amazon EU')).toBeInTheDocument())
    expect(screen.getByText('Alter Partner')).toBeInTheDocument()
  })

  it('shows inactive badge for deactivated partners', async () => {
    setup()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, () =>
        HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => screen.getByText('Alter Partner'))
    expect(screen.getByText('Inaktiv')).toBeInTheDocument()
    expect(screen.getByLabelText('Leistungstyp Gesellschafter')).toBeInTheDocument()
  })

  it('renders service type badges deduplicated per partner', async () => {
    setup()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, () =>
        HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    const amazonCell = await screen.findByText('Amazon EU')
    const amazonRow = amazonCell.closest('tr')
    expect(amazonRow).not.toBeNull()
    if (!amazonRow) {
      throw new Error('Partner row not found')
    }
    const rowQueries = within(amazonRow)

    expect(rowQueries.getAllByLabelText('Leistungstyp Lieferant')).toHaveLength(1)
    expect(rowQueries.getByLabelText('Leistungstyp Unbekannt')).toBeInTheDocument()
  })

  it('shows empty state when no partners', async () => {
    setup()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, () =>
        HttpResponse.json({ items: [], total: 0, page: 1, size: 30, pages: 1 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(screen.getByText(/keine partner/i)).toBeInTheDocument())
  })

  it('shows error state on failure', async () => {
    setup()
    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, () =>
        HttpResponse.json({ detail: 'error' }, { status: 500 }),
      ),
    )
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(screen.getByText(/fehler/i)).toBeInTheDocument())
  })

  it('searches across the full dataset via backend query params', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, ({ request }) => {
        const url = new URL(request.url)
        const search = url.searchParams.get('search') ?? ''
        const page = url.searchParams.get('page') ?? '1'

        if (search === 'Zebra') {
          expect(page).toBe('1')
          return HttpResponse.json({
            items: [
              {
                id: 'p99',
                name: 'Zebra GmbH',
                display_name: null,
                is_active: true,
                service_types: ['supplier'],
                iban_count: 0,
                name_count: 0,
                journal_line_count: 1,
                created_at: '2025-01-01T00:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            size: 30,
            pages: 1,
          })
        }

        return HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Amazon EU')).toBeInTheDocument())

    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText(/suche/i), { target: { value: 'Zebra' } })
    })

    await waitFor(() => expect(screen.getByText('Zebra GmbH')).toBeInTheDocument())
    expect(screen.queryByText('Amazon EU')).not.toBeInTheDocument()
  })

  it('keeps focus in the search field while results are refetched', async () => {
    setup()

    let resolveSearchRequest: (() => void) | null = null

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, async ({ request }) => {
        const url = new URL(request.url)
        const search = url.searchParams.get('search') ?? ''

        if (search === 'A') {
          await new Promise<void>((resolve) => {
            resolveSearchRequest = resolve
          })
          return HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 })
        }

        return HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 })
      }),
    )

    await act(async () => {
      renderPage()
    })

    const searchInput = await screen.findByPlaceholderText(/suche/i)
    searchInput.focus()
    expect(searchInput).toHaveFocus()

    await act(async () => {
      fireEvent.change(searchInput, { target: { value: 'A' } })
    })

    expect(searchInput).toHaveFocus()

    await act(async () => {
      resolveSearchRequest?.()
    })

    await waitFor(() => expect(searchInput).toHaveFocus())
  })

  it('sorts partner list by clicked columns via backend query params', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, ({ request }) => {
        const url = new URL(request.url)
        const sortBy = url.searchParams.get('sort_by') ?? 'name'
        const sortDir = url.searchParams.get('sort_dir') ?? 'asc'

        if (sortBy === 'journal_line_count' && sortDir === 'asc') {
          return HttpResponse.json({
            items: [...PARTNERS].sort((left, right) => left.journal_line_count - right.journal_line_count),
            total: 2,
            page: 1,
            size: 30,
            pages: 1,
          })
        }

        return HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Amazon EU')).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Buchungen sortieren' }))
    })

    await waitFor(() => {
      const rows = screen.getAllByRole('row')
      expect(within(rows[1]).getByText('Alter Partner')).toBeInTheDocument()
    })
  })

  it('filters partner list by selected service type via backend query params', async () => {
    setup()

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, ({ request }) => {
        const url = new URL(request.url)
        const serviceType = url.searchParams.get('service_type') ?? ''

        if (serviceType === 'shareholder') {
          return HttpResponse.json({
            items: [PARTNERS[1]],
            total: 1,
            page: 1,
            size: 30,
            pages: 1,
          })
        }

        return HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Amazon EU')).toBeInTheDocument())

    await act(async () => {
      fireEvent.change(screen.getByRole('combobox', { name: 'Leistungstyp filtern' }), { target: { value: 'shareholder' } })
    })

    await waitFor(() => expect(screen.getByText('Alter Partner')).toBeInTheDocument())
    expect(screen.queryByText('Amazon EU')).not.toBeInTheDocument()
  })

  it('creates a new partner with manual_assignment checked', async () => {
    setup()
    const user = userEvent.setup()
    let capturedBody: Record<string, unknown> = {}

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/partners`, () =>
        HttpResponse.json({ items: PARTNERS, total: 2, page: 1, size: 30, pages: 1 }),
      ),
      http.post(`/api/v1/mandants/${MANDANT_ID}/partners`, async ({ request }) => {
        capturedBody = await request.json() as Record<string, unknown>
        return HttpResponse.json(
          { ...PARTNERS[0], id: 'p-new', name: capturedBody.name as string, manual_assignment: capturedBody.manual_assignment },
          { status: 201 },
        )
      }),
    )

    await act(async () => { renderPage() })
    await waitFor(() => expect(screen.getByText('Amazon EU')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /neuer partner/i }))
    await user.type(screen.getByPlaceholderText('Partnername'), 'Neuer Lieferant')

    const manualCheckbox = screen.getByRole('checkbox', { name: /manuelle zuordnung/i })
    expect(manualCheckbox).not.toBeChecked()
    await user.click(manualCheckbox)
    expect(manualCheckbox).toBeChecked()

    await user.click(screen.getByRole('button', { name: /anlegen/i }))

    await waitFor(() => {
      expect(capturedBody.name).toBe('Neuer Lieferant')
      expect(capturedBody.manual_assignment).toBe(true)
    })
  })
})
