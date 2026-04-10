import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ForgotPassword } from '@/pages/ForgotPassword'

function renderPage() {
  return render(
    <MemoryRouter>
      <ForgotPassword />
    </MemoryRouter>,
  )
}

describe('ForgotPassword', () => {
  it('renders email field and submit button', () => {
    renderPage()
    expect(screen.getByLabelText(/e-mail/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reset-link/i })).toBeInTheDocument()
  })

  it('shows success message after submit regardless of email', async () => {
    renderPage()
    fireEvent.change(screen.getByLabelText(/e-mail/i), {
      target: { value: 'any@email.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /reset-link/i }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/falls diese/i)
    })
  })

  it('shows success even for unknown email (anti-enumeration)', async () => {
    renderPage()
    fireEvent.change(screen.getByLabelText(/e-mail/i), {
      target: { value: 'unknown@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /reset-link/i }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  it('shows validation error for invalid email', async () => {
    renderPage()
    fireEvent.change(screen.getByLabelText(/e-mail/i), {
      target: { value: 'not-an-email' },
    })
    fireEvent.click(screen.getByRole('button', { name: /reset-link/i }))
    await waitFor(() => {
      expect(screen.getByText(/ungültige/i)).toBeInTheDocument()
    })
  })

  it('has a back to login link', () => {
    renderPage()
    expect(screen.getByRole('link', { name: /zurück/i })).toHaveAttribute('href', '/login')
  })
})
