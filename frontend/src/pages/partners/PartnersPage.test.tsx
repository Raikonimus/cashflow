import { act, render, screen, waitFor } from '@testing-library/react'
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
      user: { sub: 'u1', email: 'x@x.com', role, mandant_id: MANDANT_ID },
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
    iban_count: 2,
    name_count: 1,
    pattern_count: 0,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'p2',
    name: 'Alter Partner',
    is_active: false,
    iban_count: 0,
    name_count: 0,
    pattern_count: 0,
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
})
