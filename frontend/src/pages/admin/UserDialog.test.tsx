import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import type { UserListItem } from '@/api/users'
import { UserDialog } from './UserDialog'

const ZUORDENBAR = [
  { id: 'm1', name: 'Mandant A' },
  { id: 'm2', name: 'Mandant B' },
]

/** Antwortet auf die Abfrage der zuordenbaren Mandanten. */
function mandantenHandler(mandanten = ZUORDENBAR) {
  return http.get('/api/v1/users/assignable-mandants', () => HttpResponse.json(mandanten))
}

function zeichne(user?: UserListItem) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onClose = vi.fn()
  return {
    onClose,
    ...render(
      <QueryClientProvider client={qc}>
        <UserDialog user={user} onClose={onClose} />
      </QueryClientProvider>,
    ),
  }
}

const BESTEHENDER: UserListItem = {
  id: 'u1',
  email: 'alice@test.com',
  role: 'accountant',
  is_active: true,
  invitation_status: 'accepted',
  mandants: [{ id: 'm1', name: 'Mandant A' }],
}

describe('UserDialog', () => {
  it('zeigt die zuordenbaren Mandanten zur Auswahl', async () => {
    server.use(mandantenHandler())
    zeichne()

    expect(await screen.findByLabelText('Mandant A')).toBeInTheDocument()
    expect(screen.getByLabelText('Mandant B')).toBeInTheDocument()
  })

  it('sendet die gewählten Mandanten beim Anlegen mit', async () => {
    // Der Kern von Befund M7: Vorher gab es diesen Weg gar nicht — ein neu
    // angelegter Benutzer blieb ohne Mandanten und kam an keine Daten.
    let gesendet: Record<string, unknown> | null = null
    server.use(
      mandantenHandler(),
      http.post('/api/v1/users', async ({ request }) => {
        gesendet = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...BESTEHENDER, id: 'neu' }, { status: 201 })
      }),
    )

    const { onClose } = zeichne()
    await screen.findByLabelText('Mandant A')

    await act(async () => {
      fireEvent.change(screen.getByLabelText('E-Mail'), {
        target: { value: 'neu@test.com' },
      })
      fireEvent.click(screen.getByLabelText('Mandant B'))
      fireEvent.click(screen.getByRole('button', { name: 'Anlegen' }))
    })

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(gesendet).toMatchObject({
      email: 'neu@test.com',
      mandant_ids: ['m2'],
    })
  })

  it('belegt die Auswahl beim Bearbeiten mit dem bestehenden Stand vor', async () => {
    server.use(mandantenHandler())
    zeichne(BESTEHENDER)

    const a = (await screen.findByLabelText('Mandant A')) as HTMLInputElement
    const b = screen.getByLabelText('Mandant B') as HTMLInputElement
    expect(a.checked).toBe(true)
    expect(b.checked).toBe(false)
  })

  it('sendet den Sollstand beim Bearbeiten', async () => {
    let gesendet: Record<string, unknown> | null = null
    server.use(
      mandantenHandler(),
      http.patch('/api/v1/users/u1', async ({ request }) => {
        gesendet = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(BESTEHENDER)
      }),
    )

    zeichne(BESTEHENDER)
    await screen.findByLabelText('Mandant A')

    await act(async () => {
      fireEvent.click(screen.getByLabelText('Mandant B'))
      fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    })

    await waitFor(() => expect(gesendet).not.toBeNull())
    expect(gesendet).toMatchObject({ mandant_ids: ['m1', 'm2'] })
  })

  it('warnt, wenn kein Mandant gewählt ist', async () => {
    server.use(mandantenHandler())
    zeichne()

    await screen.findByLabelText('Mandant A')
    expect(screen.getByText(/ohne mandant kommt der benutzer an keine daten/i)).toBeInTheDocument()
  })

  it('nennt Zuordnungen, die hier nicht geändert werden können', async () => {
    // Ein Mandant-Admin sieht nur seine eigenen Mandanten. Hat der Benutzer weitere
    // Zuordnungen, bleiben sie beim Speichern erhalten — das muss dastehen, sonst
    // wirkt die Liste wie der vollständige Stand.
    server.use(mandantenHandler([{ id: 'm1', name: 'Mandant A' }]))
    zeichne({
      ...BESTEHENDER,
      mandants: [
        { id: 'm1', name: 'Mandant A' },
        { id: 'm2', name: 'Mandant B' },
      ],
    })

    await screen.findByLabelText('Mandant A')
    expect(await screen.findByText(/zusätzlich zugeordnet: Mandant B/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Mandant B')).not.toBeInTheDocument()
  })

  it('zeigt die Fehlermeldung des Servers', async () => {
    server.use(
      mandantenHandler(),
      http.patch('/api/v1/users/u1', () =>
        HttpResponse.json({ detail: 'Insufficient permissions for this mandant' }, { status: 403 }),
      ),
    )

    zeichne(BESTEHENDER)
    await screen.findByLabelText('Mandant A')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    })

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
