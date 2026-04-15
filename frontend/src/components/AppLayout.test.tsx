import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AppLayout } from './AppLayout'
import { useAuthStore } from '@/store/auth-store'

vi.mock('@/api/review', () => ({
  listReviewItems: vi.fn(async () => ({ items: [], total: 0, page: 1, size: 1, pages: 1 })),
}))

vi.mock('@/api/auth', () => ({
  logoutUser: vi.fn(async () => undefined),
}))

function renderLayout(initialPath = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<div>Dashboard</div>} />
            <Route path="/accounts" element={<div>Konten Seite</div>} />
            <Route path="/settings/service-keywords" element={<div>Keywords Seite</div>} />
            <Route path="/admin/audit" element={<div>Audit Seite</div>} />
            <Route path="/admin/mandants" element={<div>Mandanten Seite</div>} />
            <Route path="/admin/users" element={<div>Benutzer Seite</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AppLayout', () => {
  afterEach(() => {
    act(() => {
      useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
    })
  })

  it('groups settings links in the settings menu', async () => {
    act(() => {
      useAuthStore.setState({
        token: 'tok',
        user: { sub: 'u1', role: 'admin', mandant_id: 'mandant-1' },
        selectedMandant: { id: 'mandant-1', name: 'Testmandant' },
        mandants: [],
      })
    })

    renderLayout()

    await waitFor(() => expect(screen.getByRole('button', { name: 'Einstellungen' })).toBeInTheDocument())

    expect(screen.queryByRole('link', { name: 'Konten' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Service-Keywords' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Audit-Log' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Mandanten' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Benutzer' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Einstellungen' }))

    expect(screen.getByRole('link', { name: 'Konten' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Service-Keywords' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Audit-Log' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mandanten' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Benutzer' })).toBeInTheDocument()
  })
})