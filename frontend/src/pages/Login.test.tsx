import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { Login } from '@/pages/Login'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'

function renderLogin(initialPath = '/login') {
  const router = createMemoryRouter(
    [
      { path: '/login', element: <Login /> },
      { path: '/login/select-mandant', element: <div>Select Mandant Page</div> },
      { path: '/', element: <div>Dashboard Page</div> },
    ],
    { initialEntries: [initialPath] },
  )
  return { router, ...render(<RouterProvider router={router} />) }
}

describe('Login', () => {
  it('renders email and password fields', () => {
    renderLogin()
    expect(screen.getByLabelText(/e-mail/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/passwort/i)).toBeInTheDocument()
  })

  it('renders forgot password link', () => {
    renderLogin()
    expect(screen.getByRole('link', { name: /passwort vergessen/i })).toBeInTheDocument()
  })

  it('shows validation error for invalid email', async () => {
    renderLogin()
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/e-mail/i), {
        target: { value: 'not-an-email' },
      })
      fireEvent.change(screen.getByLabelText(/passwort/i), {
        target: { value: 'pw' },
      })
      fireEvent.click(screen.getByRole('button', { name: /anmelden/i }))
    })
    await waitFor(() => {
      expect(screen.getByText(/ungültige e-mail/i)).toBeInTheDocument()
    })
  })

  it('shows error message on invalid credentials', async () => {
    renderLogin()
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/e-mail/i), {
        target: { value: 'wrong@test.com' },
      })
      fireEvent.change(screen.getByLabelText(/passwort/i), {
        target: { value: 'wrong' },
      })
      fireEvent.click(screen.getByRole('button', { name: /anmelden/i }))
    })
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/ungültig/i)
    })
  })

  it('redirects to / on successful single-mandant login', async () => {
    const { router } = renderLogin()
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/e-mail/i), {
        target: { value: 'test@example.com' },
      })
      fireEvent.change(screen.getByLabelText(/passwort/i), {
        target: { value: 'password' },
      })
      fireEvent.click(screen.getByRole('button', { name: /anmelden/i }))
    })
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/')
    })
  })

  it('redirects to /login/select-mandant when multiple mandants', async () => {
    const { router } = renderLogin()
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/e-mail/i), {
        target: { value: 'multi@example.com' },
      })
      fireEvent.change(screen.getByLabelText(/passwort/i), {
        target: { value: 'password' },
      })
      fireEvent.click(screen.getByRole('button', { name: /anmelden/i }))
    })
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login/select-mandant')
    })
  })

  it('shows loading state while submitting', async () => {
    server.use(
      http.post('/api/v1/auth/login', async () => {
        await new Promise((r) => setTimeout(r, 100))
        return HttpResponse.json({
          access_token: 't',
          mandants: [{ id: 'm1', name: 'Test' }],
          requires_mandant_selection: false,
        })
      }),
    )
    renderLogin()
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: 'test@example.com' } })
      fireEvent.change(screen.getByLabelText(/passwort/i), { target: { value: 'password' } })
      fireEvent.click(screen.getByRole('button', { name: /anmelden/i }))
    })
    expect(screen.getByRole('button', { name: /anmelden…/i })).toBeDisabled()
  })
})
