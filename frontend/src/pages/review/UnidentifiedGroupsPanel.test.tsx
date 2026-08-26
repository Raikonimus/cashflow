import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import type { ResolveGroupRequest, UnidentifiedGroups } from '@/api/review'
import { UnidentifiedGroupsPanel } from './UnidentifiedGroupsPanel'

const listMock = vi.hoisted(() => vi.fn())
const resolveMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/review', () => ({
  listUnidentifiedGroups: listMock,
  resolveUnidentifiedGroup: resolveMock,
}))

const GROUPS: UnidentifiedGroups = {
  total_open: 5,
  grouped: 5,
  groups: [
    {
      key: 'ANTHROPIC',
      suggested_pattern: 'ANTHROPIC',
      suggested_partner_name: 'Anthropic',
      line_count: 4,
      total_amount: '-398.33',
      first_date: '2026-01-02',
      last_date: '2026-03-04',
      sample_texts: ['ANTHROPIC inkl. Fremdwährungsentgelt 1,32', 'ANTHROPIC* CLAUDE SUB'],
      item_ids: ['i1', 'i2', 'i3', 'i4'],
    },
    {
      key: 'MSFT',
      suggested_pattern: 'MSFT',
      suggested_partner_name: 'Msft',
      line_count: 1,
      total_amount: '-22.50',
      first_date: '2026-01-20',
      last_date: '2026-01-20',
      sample_texts: ['MSFT * E0301094XL'],
      item_ids: ['i5'],
    },
  ],
}

function renderPanel(onNotice = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const result = render(
    <QueryClientProvider client={queryClient}>
      <UnidentifiedGroupsPanel onNotice={onNotice} />
    </QueryClientProvider>,
  )
  return { ...result, onNotice }
}

function cardFor(key: string): HTMLElement {
  const heading = screen.getByText(key)
  const card = heading.closest('div.rounded-xl')
  if (!card) throw new Error(`Karte für ${key} nicht gefunden`)
  return card as HTMLElement
}

describe('UnidentifiedGroupsPanel', () => {
  beforeEach(() => {
    listMock.mockReset()
    resolveMock.mockReset()
    listMock.mockResolvedValue(GROUPS)
    resolveMock.mockResolvedValue({
      partner_id: 'p1', partner_name: 'Anthropic', service_id: 's1', matcher_id: 'm1',
      resolved_items: 4, assigned_lines: 4,
    })
    act(() => {
      useAuthStore.setState({
        token: 'tok',
        user: { sub: 'u1', role: 'accountant', mandant_id: 'mandant-1' },
        selectedMandant: null,
        mandants: [],
      })
    })
  })

  afterEach(() => {
    act(() => {
      useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
    })
  })

  it('zeigt nichts an, wenn es keine Gruppen gibt', async () => {
    listMock.mockResolvedValue({ groups: [], total_open: 0, grouped: 0 })
    const { container } = renderPanel()
    await waitFor(() => expect(listMock).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('fasst die offenen Buchungen nach Haendler zusammen', async () => {
    renderPanel()
    expect(await screen.findByText('ANTHROPIC')).toBeInTheDocument()
    expect(screen.getByText('MSFT')).toBeInTheDocument()

    const anthropic = cardFor('ANTHROPIC')
    expect(within(anthropic).getByText(/4 Buchungen/)).toBeInTheDocument()
    expect(within(anthropic).getByText(/-398,33 €/)).toBeInTheDocument()
    expect(within(anthropic).getByText(/02\.01\.2026 – 04\.03\.2026/)).toBeInTheDocument()
    // Einzahl bei genau einer Buchung.
    expect(cardFor('MSFT').textContent).toMatch(/1 Buchung ·/)
  })

  it('blendet Beispieltexte auf Wunsch ein', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    expect(screen.queryByText('ANTHROPIC* CLAUDE SUB')).not.toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: /Beispieltext/ }))
    expect(screen.getByText('ANTHROPIC* CLAUDE SUB')).toBeInTheDocument()
  })

  it('legt Partner, Leistung und Matcher mit den Vorschlagswerten an', async () => {
    const { onNotice } = renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ }))
    })

    await waitFor(() => expect(resolveMock).toHaveBeenCalledTimes(1))
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload).toEqual({
      item_ids: ['i1', 'i2', 'i3', 'i4'],
      pattern: 'ANTHROPIC',
      service_name: 'Anthropic',
      partner_name: 'Anthropic',
    })
    expect(onNotice).toHaveBeenCalledWith('success', expect.stringContaining('4 Buchung(en) zugeordnet'))
  })

  it('uebernimmt geaenderte Eingaben', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    fireEvent.change(within(card).getByLabelText('Partner für ANTHROPIC'), { target: { value: 'Anthropic PBC' } })
    fireEvent.change(within(card).getByLabelText('Leistung für ANTHROPIC'), { target: { value: 'Claude Max' } })
    fireEvent.change(within(card).getByLabelText('Matcher-Muster für ANTHROPIC'), { target: { value: 'anthropic' } })

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ }))
    })

    await waitFor(() => expect(resolveMock).toHaveBeenCalled())
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload.partner_name).toBe('Anthropic PBC')
    expect(payload.service_name).toBe('Claude Max')
    expect(payload.pattern).toBe('anthropic')
  })

  it('sperrt das Anlegen bei leerem Feld oder zu kurzem Muster', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))
    const submit = within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ })

    fireEvent.change(within(card).getByLabelText('Partner für ANTHROPIC'), { target: { value: '  ' } })
    expect(submit).toBeDisabled()

    fireEvent.change(within(card).getByLabelText('Partner für ANTHROPIC'), { target: { value: 'Anthropic' } })
    fireEvent.change(within(card).getByLabelText('Matcher-Muster für ANTHROPIC'), { target: { value: 'A' } })
    expect(submit).toBeDisabled()

    fireEvent.change(within(card).getByLabelText('Matcher-Muster für ANTHROPIC'), { target: { value: 'AN' } })
    expect(submit).toBeEnabled()
  })

  it('meldet einen Fehler mit dem Grund aus der Antwort', async () => {
    resolveMock.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: 'Keine offenen Items dieser Gruppe gefunden' } },
    })
    const { onNotice } = renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ }))
    })

    await waitFor(() =>
      expect(onNotice).toHaveBeenCalledWith('error', 'Keine offenen Items dieser Gruppe gefunden'),
    )
  })
})
