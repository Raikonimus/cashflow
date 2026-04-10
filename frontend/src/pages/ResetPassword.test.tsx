import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ResetPassword } from '@/pages/ResetPassword'

function renderWithToken(token?: string) {
  const search = token ? `?token=${token}` : ''
  return render(
    <MemoryRouter initialEntries={[`/reset-password${search}`]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ResetPassword', () => {
  it('shows error page if token is missing', () => {
    renderWithToken()
    expect(screen.getByText(/fehlender reset-link/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /neuen reset-link/i })).toBeInTheDocument()
  })

  it('shows password form when token is present', () => {
    renderWithToken('some-token')
    expect(screen.getByLabelText(/neues passwort/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/passwort bestätigen/i)).toBeInTheDocument()
  })

  it('shows validation error for short password', async () => {
    renderWithToken('some-token')
    fireEvent.change(screen.getByLabelText(/neues passwort/i), {
      target: { value: 'short' },
    })
    fireEvent.change(screen.getByLabelText(/passwort bestätigen/i), {
      target: { value: 'short' },
    })
    fireEvent.click(screen.getByRole('button', { name: /speichern/i }))
    await waitFor(() => {
      expect(screen.getByText(/mindestens 8/i)).toBeInTheDocument()
    })
  })

  it('shows validation error when passwords do not match', async () => {
    renderWithToken('some-token')
    fireEvent.change(screen.getByLabelText(/neues passwort/i), {
      target: { value: 'password123' },
    })
    fireEvent.change(screen.getByLabelText(/passwort bestätigen/i), {
      target: { value: 'different456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /speichern/i }))
    await waitFor(() => {
      expect(screen.getByText(/stimmen nicht/i)).toBeInTheDocument()
    })
  })

  it('shows error when token is invalid', async () => {
    renderWithToken('invalid-token')
    fireEvent.change(screen.getByLabelText(/neues passwort/i), {
      target: { value: 'newpassword1' },
    })
    fireEvent.change(screen.getByLabelText(/passwort bestätigen/i), {
      target: { value: 'newpassword1' },
    })
    fireEvent.click(screen.getByRole('button', { name: /speichern/i }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/ungültig oder abgelaufen/i)
    })
  })

  it('redirects to /login on successful reset', async () => {
    renderWithToken('valid-token')
    fireEvent.change(screen.getByLabelText(/neues passwort/i), {
      target: { value: 'newpassword1' },
    })
    fireEvent.change(screen.getByLabelText(/passwort bestätigen/i), {
      target: { value: 'newpassword1' },
    })
    fireEvent.click(screen.getByRole('button', { name: /speichern/i }))
    await waitFor(() => {
      expect(screen.getByText(/login page/i)).toBeInTheDocument()
    })
  })
})
