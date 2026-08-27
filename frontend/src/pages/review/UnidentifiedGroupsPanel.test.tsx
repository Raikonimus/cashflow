import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import type { ResolveGroupRequest, UnidentifiedGroups } from '@/api/review'
import { UnidentifiedGroupsPanel } from './UnidentifiedGroupsPanel'

const listMock = vi.hoisted(() => vi.fn())
const resolveMock = vi.hoisted(() => vi.fn())
const listPartnersMock = vi.hoisted(() => vi.fn())
const listServicesMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/review', () => ({
  listUnidentifiedGroups: listMock,
  resolveUnidentifiedGroup: resolveMock,
}))

vi.mock('@/api/partners', () => ({ listPartners: listPartnersMock }))
vi.mock('@/api/services', () => ({ listPartnerServices: listServicesMock }))

const MICROSOFT = { id: 'p-msft', name: 'Microsoft Ireland', is_active: true }
const SERVICES = [
  { id: 'svc-base', partner_id: 'p-msft', name: 'Basisleistung', is_base_service: true },
  { id: 'svc-lic', partner_id: 'p-msft', name: 'Lizenzen', is_base_service: false },
]

/** Bestehenden Partner in einer Karte auswaehlen. */
async function pickExistingPartner(card: HTMLElement, key: string, name = MICROSOFT.name) {
  fireEvent.click(within(card).getByRole('button', { name: `Bestehender für ${key}` }))
  fireEvent.change(within(card).getByLabelText(`Partner suchen für ${key}`), { target: { value: 'micro' } })
  await act(async () => {
    fireEvent.click(await within(card).findByRole('button', { name }))
  })
}

const GROUPS: UnidentifiedGroups = {
  total_open: 5,
  grouped: 5,
  groups: [
    {
      key: 'ANTHROPIC',
      suggested_pattern: 'ANTHROPIC',
      suggested_partner_id: null,
      suggested_partner_name: 'Anthropic',
      line_count: 4,
      total_amount: '-398.33',
      first_date: '2026-01-02',
      last_date: '2026-03-04',
      lines: [
        { id: 'l1', valuta_date: '2026-01-02', amount: '-99.58', text: 'ANTHROPIC inkl. Fremdwährungsentgelt 1,32' },
        { id: 'l2', valuta_date: '2026-01-30', amount: '-99.58', text: 'ANTHROPIC* CLAUDE SUB' },
        { id: 'l3', valuta_date: '2026-02-28', amount: '-99.58', text: 'ANTHROPIC* CLAUDE SUB' },
        { id: 'l4', valuta_date: '2026-03-04', amount: '-99.59', text: null },
      ],
      item_ids: ['i1', 'i2', 'i3', 'i4'],
    },
    {
      key: 'MSFT',
      suggested_pattern: 'MSFT',
      suggested_partner_id: null,
      suggested_partner_name: 'Msft',
      line_count: 1,
      total_amount: '-22.50',
      first_date: '2026-01-20',
      last_date: '2026-01-20',
      lines: [{ id: 'l5', valuta_date: '2026-01-20', amount: '-22.50', text: 'MSFT * E0301094XL' }],
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
    listPartnersMock.mockReset()
    listServicesMock.mockReset()
    listMock.mockResolvedValue(GROUPS)
    listPartnersMock.mockResolvedValue({ items: [MICROSOFT], total: 1, page: 1, size: 8, pages: 1 })
    listServicesMock.mockResolvedValue(SERVICES)
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

  it('blendet die einzelnen Buchungszeilen auf Wunsch ein', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: '4 Buchung(en) anzeigen' }))

    const rows = within(within(card).getByRole('table')).getAllByRole('row')
    // Kopfzeile plus eine Zeile je Buchung.
    expect(rows).toHaveLength(5)
    expect(within(rows[1]).getByText('02.01.2026')).toBeInTheDocument()
    expect(within(rows[1]).getByText('ANTHROPIC inkl. Fremdwährungsentgelt 1,32')).toBeInTheDocument()
    expect(within(rows[1]).getByText('-99,58 €')).toBeInTheDocument()
    // Gleicher Text mehrfach: nichts wird zusammengefasst.
    expect(within(card).getAllByText('ANTHROPIC* CLAUDE SUB')).toHaveLength(2)
    // Leerer Buchungstext bleibt als Zeile sichtbar.
    expect(within(rows[4]).getByText('—')).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: 'Buchungen ausblenden' }))
    expect(within(card).queryByRole('table')).not.toBeInTheDocument()
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

  it('startet beim bereits vorhandenen Partner statt bei "neu anlegen"', async () => {
    listMock.mockResolvedValue({
      ...GROUPS,
      groups: [{
        ...GROUPS.groups[1],
        key: 'WEAVIATE B.V',
        suggested_pattern: 'WEAVIATE B.V',
        // Der Server hat den Haendler als bestehenden Partner erkannt; der
        // Vorschlag traegt dessen echten Namen, nicht die verschoenerte Form.
        suggested_partner_id: 'p-weaviate',
        suggested_partner_name: 'WEAVIATE B.V.',
      }],
    })
    renderPanel()
    const card = cardFor(await screen.findByText('WEAVIATE B.V').then(() => 'WEAVIATE B.V'))

    expect(within(card).getByRole('button', { name: 'Bestehender für WEAVIATE B.V' })).toHaveAttribute(
      'aria-pressed', 'true',
    )
    expect(within(card).getByText('WEAVIATE B.V.')).toBeInTheDocument()
    expect(within(card).getByText(/Bereits vorhanden/)).toBeInTheDocument()
    expect(within(card).queryByLabelText('Partner für WEAVIATE B.V')).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 1 Buchung/ }))
    })
    await waitFor(() => expect(resolveMock).toHaveBeenCalled())
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload.partner_id).toBe('p-weaviate')
    expect(payload.partner_name).toBeUndefined()
  })

  it('laesst den vorgeschlagenen Partner verwerfen', async () => {
    listMock.mockResolvedValue({
      ...GROUPS,
      groups: [{ ...GROUPS.groups[1], suggested_partner_id: 'p-msft', suggested_partner_name: 'Microsoft Ireland' }],
    })
    renderPanel()
    const card = cardFor(await screen.findByText('MSFT').then(() => 'MSFT'))

    fireEvent.click(within(card).getByRole('button', { name: 'Neu anlegen für MSFT' }))
    const input = within(card).getByLabelText('Partner für MSFT')
    fireEvent.change(input, { target: { value: 'Microsoft Corp' } })

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 1 Buchung/ }))
    })
    await waitFor(() => expect(resolveMock).toHaveBeenCalled())
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload.partner_name).toBe('Microsoft Corp')
    expect(payload.partner_id).toBeUndefined()
  })

  it('ordnet die Gruppe einem bestehenden Partner zu', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await pickExistingPartner(card, 'ANTHROPIC')
    expect(listPartnersMock).toHaveBeenCalledWith('mandant-1', 1, 8, false, 'micro')
    // Der gewaehlte Partner ersetzt das Suchfeld.
    expect(within(card).queryByLabelText('Partner suchen für ANTHROPIC')).not.toBeInTheDocument()
    expect(within(card).getByText('Microsoft Ireland')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ }))
    })

    await waitFor(() => expect(resolveMock).toHaveBeenCalled())
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload.partner_id).toBe('p-msft')
    expect(payload.partner_name).toBeUndefined()
    // Ohne Auswahl in der Liste bleibt es bei einer neuen Leistung.
    expect(payload.service_name).toBe('Anthropic')
  })

  it('haengt den Matcher an eine bestehende Leistung des Partners', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await pickExistingPartner(card, 'ANTHROPIC')
    const select = await within(card).findByRole('combobox', { name: 'Leistung für ANTHROPIC' })
    expect(listServicesMock).toHaveBeenCalledWith('mandant-1', 'p-msft')
    expect(within(select).getByRole('option', { name: 'Lizenzen' })).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'svc-lic' } })
    // Bei bestehender Leistung entfaellt das Namensfeld.
    expect(within(card).queryByLabelText('Name der neuen Leistung für ANTHROPIC')).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ }))
    })

    await waitFor(() => expect(resolveMock).toHaveBeenCalled())
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload.service_id).toBe('svc-lic')
    expect(payload.service_name).toBeUndefined()
  })

  it('bietet die Basisleistung nicht als Matcher-Ziel an', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await pickExistingPartner(card, 'ANTHROPIC')
    const select = await within(card).findByRole('combobox', { name: 'Leistung für ANTHROPIC' })
    // Ein Matcher an der Basisleistung greift weder bei der Partnererkennung
    // noch bei der Leistungszuordnung.
    expect(within(select).queryByRole('option', { name: 'Basisleistung' })).not.toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'Lizenzen' })).toBeInTheDocument()
  })

  it('faellt auf ein Namensfeld zurueck, wenn der Partner nur die Basisleistung hat', async () => {
    listServicesMock.mockResolvedValue([SERVICES[0]])
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await pickExistingPartner(card, 'ANTHROPIC')
    await waitFor(() => expect(listServicesMock).toHaveBeenCalled())
    expect(within(card).queryByRole('combobox', { name: 'Leistung für ANTHROPIC' })).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ }))
    })
    await waitFor(() => expect(resolveMock).toHaveBeenCalled())
    const [, payload] = resolveMock.mock.calls[0] as [string, ResolveGroupRequest]
    expect(payload.service_name).toBe('Anthropic')
    expect(payload.service_id).toBeUndefined()
  })

  it('verwirft die Leistungsauswahl beim Partnerwechsel', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    await pickExistingPartner(card, 'ANTHROPIC')
    fireEvent.change(await within(card).findByRole('combobox', { name: 'Leistung für ANTHROPIC' }), { target: { value: 'svc-lic' } })

    fireEvent.click(within(card).getByRole('button', { name: 'Ändern' }))
    await pickExistingPartner(card, 'ANTHROPIC')

    const select = await within(card).findByRole('combobox', { name: 'Leistung für ANTHROPIC' })
    expect((select as HTMLSelectElement).value).toBe('')
  })

  it('sperrt das Anlegen, solange kein bestehender Partner gewaehlt ist', async () => {
    renderPanel()
    const card = cardFor(await screen.findByText('ANTHROPIC').then(() => 'ANTHROPIC'))

    fireEvent.click(within(card).getByRole('button', { name: 'Bestehender für ANTHROPIC' }))
    expect(within(card).getByRole('button', { name: /Anlegen & 4 Buchung/ })).toBeDisabled()
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
