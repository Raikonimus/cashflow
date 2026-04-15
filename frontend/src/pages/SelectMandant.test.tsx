import { act, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { SelectMandant } from '@/pages/SelectMandant'
import { useAuthStore } from '@/store/auth-store'
import { createTestJwt } from '@/test/jwt'

function renderWithMandants() {
  act(() => {
    useAuthStore.setState({
      token: createTestJwt({ sub: 'u1', role: 'accountant', mandant_id: null }),
      user: { sub: 'u1', role: 'accountant', mandant_id: null },
      mandants: [
        { id: 'mandant-1', name: 'Mandant A' },
        { id: 'mandant-2', name: 'Mandant B' },
      ],
      selectedMandant: null,
    })
  })

  const router = createMemoryRouter(
    [
      { path: '/login/select-mandant', element: <SelectMandant /> },
      { path: '/login', element: <div>Login Page</div> },
      { path: '/', element: <div>Dashboard</div> },
    ],
    { initialEntries: ['/login/select-mandant'] },
  )
  return { router, ...render(<RouterProvider router={router} />) }
}

describe('SelectMandant', () => {
  afterEach(() => {
    act(() => {
      useAuthStore.setState({ token: null, user: null, mandants: [], selectedMandant: null })
    })
  })

  it('shows list of mandants', async () => {
    renderWithMandants()
    await waitFor(() => {
      expect(screen.getByText('Mandant A')).toBeInTheDocument()
      expect(screen.getByText('Mandant B')).toBeInTheDocument()
    })
  })

  it('navigates to / after selecting a mandant', async () => {
    const { router } = renderWithMandants()
    await waitFor(() => screen.getByText('Mandant A'))
    await act(async () => {
      fireEvent.click(screen.getByText('Mandant A'))
    })
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/')
    })
  })

  it('auto-selects when exactly one mandant is available', async () => {
    act(() => {
      useAuthStore.setState({
        token: createTestJwt({ sub: 'u1', role: 'admin', mandant_id: null }),
        user: { sub: 'u1', role: 'admin', mandant_id: null },
        mandants: [{ id: 'mandant-1', name: 'Einziger Mandant' }],
        selectedMandant: null,
      })
    })

    const router = createMemoryRouter(
      [
        { path: '/login/select-mandant', element: <SelectMandant /> },
        { path: '/login', element: <div>Login Page</div> },
        { path: '/', element: <div>Dashboard</div> },
      ],
      { initialEntries: ['/login/select-mandant'] },
    )

    render(<RouterProvider router={router} />)

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/')
    })
  })
})
