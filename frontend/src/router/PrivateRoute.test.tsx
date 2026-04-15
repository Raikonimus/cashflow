import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { MandantRequiredRoute, PrivateRoute } from '@/router/PrivateRoute'
import { useAuthStore } from '@/store/auth-store'
import { createTestJwt } from '@/test/jwt'

function renderWithAuth(token: string | null) {
  act(() => {
    useAuthStore.setState({
      token,
      user: token ? { sub: 'user-1', role: 'admin', mandant_id: 'mandant-1' } : null,
      mandants: [],
      selectedMandant: null,
    })
  })

  let rendered: ReturnType<typeof render>
  act(() => {
    rendered = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<PrivateRoute />}>
            <Route path="/" element={<div>Protected Content</div>} />
          </Route>
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>,
    )
  })
  return rendered
}

describe('PrivateRoute', () => {
  afterEach(() => {
    act(() => {
      useAuthStore.setState({ token: null, user: null, mandants: [], selectedMandant: null })
    })
  })

  it('renders children when authenticated', () => {
    renderWithAuth(createTestJwt({ sub: 'user-1', role: 'admin', mandant_id: 'mandant-1' }))
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('redirects to /login when not authenticated', () => {
    renderWithAuth(null)
    expect(screen.getByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })
})

describe('MandantRequiredRoute', () => {
  afterEach(() => {
    act(() => {
      useAuthStore.setState({ token: null, user: null, mandants: [], selectedMandant: null })
    })
  })

  it('renders target route when login token already contains a single mandant_id', () => {
    act(() => {
      useAuthStore.getState().login(
        createTestJwt({ sub: 'user-1', role: 'accountant', mandant_id: 'mandant-1' }),
        [{ id: 'mandant-1', name: 'Einziger Mandant' }],
      )
    })

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<MandantRequiredRoute />}>
            <Route path="/" element={<div>Mandant Content</div>} />
          </Route>
          <Route path="/login/select-mandant" element={<div>Select Mandant Page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Mandant Content')).toBeInTheDocument()
    expect(screen.queryByText('Select Mandant Page')).not.toBeInTheDocument()
  })
})
