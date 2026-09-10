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

  it('zeigt einen einzelnen Mandanten zur Auswahl, statt ihn selbst zu waehlen', async () => {
    // Vorher waehlte diese Seite einen einzelnen Mandanten selbst aus — und
    // `Login.tsx` tat dasselbe, zwei Stellen fuer eine Entscheidung (Befund M2).
    // Jetzt legt der Server den einzigen Mandanten beim Anmelden direkt ins Token;
    // dieser Fall erreicht die Seite im Normalbetrieb gar nicht mehr. Kommt er
    // dennoch an, wird der Eintrag angezeigt und ist anklickbar — statt einer
    // Umleitung, die niemand nachvollziehen kann.
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

    expect(await screen.findByText('Einziger Mandant')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login/select-mandant')
  })

  it('erklaert den Zustand ohne Mandant statt zur Anmeldung zurueckzuschicken', async () => {
    // Befund M6. Vorher leitete diese Seite bei leerer Liste nach `/login` um — dort
    // stand die Anmeldemaske, obwohl der Nutzer angemeldet war. Ohne jede Erklaerung
    // sah es aus, als haette das Anmelden nicht funktioniert.
    act(() => {
      useAuthStore.setState({
        token: createTestJwt({ sub: 'u1', role: 'viewer', mandant_id: null }),
        user: { sub: 'u1', role: 'viewer', mandant_id: null },
        mandants: [],
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

    expect(await screen.findByText(/kein mandant zugeordnet/i)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login/select-mandant')
    expect(screen.getByRole('button', { name: /abmelden/i })).toBeInTheDocument()
  })
})
