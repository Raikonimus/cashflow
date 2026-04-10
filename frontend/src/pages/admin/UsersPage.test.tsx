import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { UsersPage } from './UsersPage'

const USERS = [
  {
    id: 'u1',
    email: 'alice@test.com',
    role: 'accountant',
    is_active: true,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'u2',
    email: 'bob@test.com',
    role: 'viewer',
    is_active: false,
    created_at: '2025-02-01T00:00:00Z',
  },
]

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UsersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('UsersPage', () => {
  it('renders user list', async () => {
    server.use(
      http.get('/api/v1/users', () => HttpResponse.json(USERS)),
    )
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('alice@test.com')).toBeInTheDocument(),
    )
    expect(screen.getByText('bob@test.com')).toBeInTheDocument()
  })

  it('shows "Keine Benutzer" when list is empty', async () => {
    server.use(http.get('/api/v1/users', () => HttpResponse.json([])))
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/keine benutzer/i)).toBeInTheDocument(),
    )
  })

  it('shows error state on API failure', async () => {
    server.use(
      http.get('/api/v1/users', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/fehler beim laden/i)).toBeInTheDocument(),
    )
  })

  it('opens UserDialog when clicking "+ Neuer Benutzer"', async () => {
    server.use(http.get('/api/v1/users', () => HttpResponse.json([])))
    renderPage()
    await waitFor(() => screen.getByText(/neuer benutzer/i))
    fireEvent.click(screen.getByText(/\+ neuer benutzer/i))
    expect(screen.getByText('Neuer Benutzer')).toBeInTheDocument()
  })

  it('shows active/inactive badges for users', async () => {
    server.use(http.get('/api/v1/users', () => HttpResponse.json(USERS)))
    renderPage()
    await waitFor(() => screen.getByText('alice@test.com'))
    // alice is active, bob is not
    expect(screen.getByText('Aktiv')).toBeInTheDocument()
    expect(screen.getByText('Inaktiv')).toBeInTheDocument()
  })
})
