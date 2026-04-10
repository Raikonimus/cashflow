import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RequireRole } from '@/router/RequireRole'
import { useAuthStore } from '@/store/auth-store'

function setUser(role: string) {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role, mandant_id: 'm1' },
      selectedMandant: null,
    })
  })
}

function renderWithRole(role: string | null, min: string) {
  if (role) setUser(role)
  else {
    act(() => {
      useAuthStore.setState({ token: null, user: null, selectedMandant: null })
    })
  }

  let rendered: ReturnType<typeof render>
  act(() => {
    rendered = render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route path="/" element={<div>Home</div>} />
          <Route element={<RequireRole min={min} />}>
            <Route path="/protected" element={<div>Protected Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
  })
  return rendered!
}

afterEach(() => {
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null })
  })
})

describe('RequireRole', () => {
  it('renders content when role meets minimum', () => {
    renderWithRole('accountant', 'accountant')
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('renders content when role exceeds minimum', () => {
    renderWithRole('admin', 'accountant')
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('redirects to / when role is below minimum', () => {
    renderWithRole('viewer', 'accountant')
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('redirects when no user is authenticated', () => {
    renderWithRole(null, 'viewer')
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('admin can access mandant_admin route', () => {
    renderWithRole('admin', 'mandant_admin')
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })
})
