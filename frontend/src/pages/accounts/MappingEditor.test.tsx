import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import type { ColumnAssignment, ColumnMapping, SaveMappingRequest } from '@/api/accounts'
import { MappingEditor } from './MappingEditor'

// Der Multipart-Upload von previewCsvColumns kommt unter jsdom nicht zurueck.
// Hier interessiert ohnehin die Zuordnungslogik des Editors, nicht der Transport.
const getMappingMock = vi.hoisted(() => vi.fn())
const saveMappingMock = vi.hoisted(() => vi.fn())
const previewCsvColumnsMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/accounts', () => ({
  getMapping: getMappingMock,
  saveMapping: saveMappingMock,
  previewCsvColumns: previewCsvColumnsMock,
}))

const ACCOUNT_ID = 'account-1'

// Kreditkarten-Export mit nur einem Datum - kein Valutadatum.
const CARD_COLUMNS = ['Eigener Kontoname', 'Buchungsdatum', 'Partnername', 'Betrag', 'Buchungs-Details']

// Der komplette Spaltensatz des Kreditkarten-Exports.
const FULL_CARD_COLUMNS = [
  'Eigener Kontoname', 'Eigene IBAN', 'Buchungsdatum', 'Partnername', 'Partner IBAN',
  'BIC/SWIFT', 'Partner Kontonummer', 'Bankleitzahl', 'Betrag', 'Währung',
  'Buchungs-Details', 'Empfänger-Überprüfung', 'Diese IBAN ist registriert auf',
]

function suggestionFor(column: string): string {
  const select = within(rowFor(column)).getByLabelText(`Zielfeld 1 für ${column}`)
  return (select as HTMLSelectElement).value
}

function renderEditor() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MappingEditor accountId={ACCOUNT_ID} />
    </QueryClientProvider>,
  )
}

async function uploadCsv(container: HTMLElement) {
  // Erst wenn die Mapping-Abfrage durch ist, rendert der Editor das Datei-Feld.
  await screen.findByText(/CSV-Datei auswählen/)
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
  await act(async () => {
    await userEvent.upload(fileInput, new File(['egal'], 'karte.csv', { type: 'text/csv' }))
  })
  await screen.findByText(/Spalten erkannt/)
}

function rowFor(column: string): HTMLElement {
  // Auf die Zelle einschraenken: manche Spaltennamen kommen auch als
  // Dropdown-Option vor ("Partnername", "Buchungsdatum").
  const cell = screen.getAllByText(column).find((el) => el.tagName === 'TD')
  const row = cell?.closest('tr')
  if (!row) throw new Error(`Zeile für ${column} nicht gefunden`)
  return row
}

function sentAssignments(): ColumnAssignment[] {
  const payload = saveMappingMock.mock.calls[0][2] as SaveMappingRequest
  return payload.column_assignments ?? []
}

describe('MappingEditor', () => {
  beforeEach(() => {
    getMappingMock.mockReset()
    saveMappingMock.mockReset()
    previewCsvColumnsMock.mockReset()
    getMappingMock.mockResolvedValue(null)
    saveMappingMock.mockResolvedValue({} as ColumnMapping)
    previewCsvColumnsMock.mockResolvedValue({
      columns: CARD_COLUMNS,
      detected_delimiter: ',',
      detected_encoding: 'utf-16',
      sample_rows: [Object.fromEntries(CARD_COLUMNS.map((c) => [c, 'x']))],
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

  it('sperrt das Speichern, solange ein Pflichtfeld keiner Spalte zugewiesen ist', async () => {
    const { container } = renderEditor()
    await uploadCsv(container)

    // Der Auto-Vorschlag trifft Buchungsdatum, Partnername, Betrag und
    // Buchungs-Details - aber kein Valutadatum, weil es die Spalte nicht gibt.
    expect(await screen.findByText(/Pflichtfeld ohne Spalte: Valutadatum/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeDisabled()
  })

  it('erlaubt einer Spalte ein zweites Zielfeld und speichert beide Zuordnungen', async () => {
    const { container } = renderEditor()
    await uploadCsv(container)
    await screen.findByText(/Pflichtfeld ohne Spalte: Valutadatum/)

    const dateRow = rowFor('Buchungsdatum')
    fireEvent.click(within(dateRow).getByRole('button', { name: '+ weiteres Zielfeld' }))
    fireEvent.change(within(dateRow).getByLabelText('Zielfeld 2 für Buchungsdatum'), {
      target: { value: 'valuta_date' },
    })
    await waitFor(() => expect(screen.queryByText(/Pflichtfeld ohne Spalte/)).not.toBeInTheDocument())

    // Mindestens eine Spalte muss fuer die Dublettenpruefung markiert sein.
    fireEvent.click(within(rowFor('Betrag')).getByRole('checkbox'))

    // Spalte bewusst ausschliessen - sie muss trotzdem als 'unused' mitgespeichert werden.
    fireEvent.change(
      within(rowFor('Eigener Kontoname')).getByLabelText('Zielfeld 1 für Eigener Kontoname'),
      { target: { value: 'unused' } },
    )

    const saveButton = screen.getByRole('button', { name: 'Speichern' })
    await waitFor(() => expect(saveButton).toBeEnabled())
    await act(async () => {
      fireEvent.click(saveButton)
    })

    await waitFor(() => expect(saveMappingMock).toHaveBeenCalledTimes(1))
    const sent = sentAssignments()
    expect(
      sent.filter((a) => a.source === 'Buchungsdatum').map((a) => a.target).sort(),
    ).toEqual(['booking_date', 'valuta_date'])
    // sort_order laeuft fortlaufend ueber die flache Liste.
    expect(sent.map((a) => a.sort_order)).toEqual(sent.map((_, i) => i))
    // Ausgeschlossene Spalten bleiben als 'unused' in der Konfiguration.
    expect(sent.filter((a) => a.source === 'Eigener Kontoname').map((a) => a.target)).toEqual(['unused'])
    // Jede CSV-Spalte ist vertreten.
    expect(new Set(sent.map((a) => a.source))).toEqual(new Set(CARD_COLUMNS))
  })

  it('laedt eine gespeicherte Mehrfachzuordnung wieder in die Oberflaeche', async () => {
    getMappingMock.mockResolvedValue({
      column_assignments: [
        { source: 'Buchungsdatum', target: 'booking_date', sort_order: 0, duplicate_check: true },
        { source: 'Buchungsdatum', target: 'valuta_date', sort_order: 1, duplicate_check: true },
        { source: 'Betrag', target: 'amount', sort_order: 2, duplicate_check: true },
      ],
      valuta_date_col: 'Buchungsdatum',
      booking_date_col: 'Buchungsdatum',
      amount_col: 'Betrag',
      partner_name_col: null,
      partner_iban_col: null,
      description_col: null,
      decimal_separator: ',',
      date_format: '%d.%m.%Y',
      delimiter: ',',
      encoding: 'utf-16',
      skip_rows: 0,
    } as ColumnMapping)

    renderEditor()
    const dateRow = await waitFor(() => rowFor('Buchungsdatum'))

    // Die Spalte erscheint einmal, mit zwei Zielfeldern.
    expect(screen.getAllByText('Buchungsdatum')).toHaveLength(1)
    expect(within(dateRow).getByLabelText('Zielfeld 1 für Buchungsdatum')).toHaveValue('booking_date')
    expect(within(dateRow).getByLabelText('Zielfeld 2 für Buchungsdatum')).toHaveValue('valuta_date')
    expect(screen.queryByText(/Pflichtfeld ohne Spalte/)).not.toBeInTheDocument()
  })

  it('entfernt ein zweites Zielfeld wieder', async () => {
    const { container } = renderEditor()
    await uploadCsv(container)

    const dateRow = rowFor('Buchungsdatum')
    fireEvent.click(within(dateRow).getByRole('button', { name: '+ weiteres Zielfeld' }))
    fireEvent.change(within(dateRow).getByLabelText('Zielfeld 2 für Buchungsdatum'), {
      target: { value: 'valuta_date' },
    })
    await waitFor(() => expect(screen.queryByText(/Pflichtfeld ohne Spalte/)).not.toBeInTheDocument())

    fireEvent.click(
      within(rowFor('Buchungsdatum')).getByRole('button', {
        name: 'Zielfeld 2 für Buchungsdatum entfernen',
      }),
    )

    expect(await screen.findByText(/Pflichtfeld ohne Spalte: Valutadatum/)).toBeInTheDocument()
  })

  it('bietet ein bereits vergebenes Zielfeld derselben Spalte nicht erneut an', async () => {
    const { container } = renderEditor()
    await uploadCsv(container)

    const dateRow = rowFor('Buchungsdatum')
    fireEvent.click(within(dateRow).getByRole('button', { name: '+ weiteres Zielfeld' }))

    const second = within(dateRow).getByLabelText('Zielfeld 2 für Buchungsdatum')
    expect(within(second).getByRole('option', { name: 'Buchungsdatum *' })).toBeDisabled()
    expect(within(second).getByRole('option', { name: 'Valutadatum *' })).toBeEnabled()
  })

  it('setzt bei "Nicht verwendet" alle anderen Zielfelder der Spalte zurueck', async () => {
    const { container } = renderEditor()
    await uploadCsv(container)

    const dateRow = rowFor('Buchungsdatum')
    fireEvent.click(within(dateRow).getByRole('button', { name: '+ weiteres Zielfeld' }))
    fireEvent.change(within(dateRow).getByLabelText('Zielfeld 2 für Buchungsdatum'), {
      target: { value: 'valuta_date' },
    })
    await waitFor(() => expect(screen.queryByText(/Pflichtfeld ohne Spalte/)).not.toBeInTheDocument())

    fireEvent.change(within(rowFor('Buchungsdatum')).getByLabelText('Zielfeld 1 für Buchungsdatum'), {
      target: { value: 'unused' },
    })

    const updated = rowFor('Buchungsdatum')
    expect(within(updated).getByLabelText('Zielfeld 1 für Buchungsdatum')).toHaveValue('unused')
    expect(within(updated).queryByLabelText('Zielfeld 2 für Buchungsdatum')).not.toBeInTheDocument()
    expect(await screen.findByText(/Pflichtfeld ohne Spalte/)).toBeInTheDocument()
  })

  describe('Auto-Vorschlag', () => {
    beforeEach(() => {
      previewCsvColumnsMock.mockResolvedValue({
        columns: FULL_CARD_COLUMNS,
        detected_delimiter: ',',
        detected_encoding: 'utf-16',
        sample_rows: [Object.fromEntries(FULL_CARD_COLUMNS.map((c) => [c, 'x']))],
      })
    })

    it('schlaegt fuer "Buchungs-Details" den Verwendungszweck vor, nicht das Buchungsdatum', async () => {
      const { container } = renderEditor()
      await uploadCsv(container)

      // 'buchungsdetail' ist laenger als 'buchung' und gewinnt deshalb.
      expect(suggestionFor('Buchungs-Details')).toBe('description')
      expect(suggestionFor('Buchungsdatum')).toBe('booking_date')
    })

    it('schliesst Spalten des eigenen Kontos aus', async () => {
      const { container } = renderEditor()
      await uploadCsv(container)

      expect(suggestionFor('Eigener Kontoname')).toBe('unused')
      expect(suggestionFor('Eigene IBAN')).toBe('unused')
    })

    it('schlaegt fuer "Buchungsreferenz" kein Datum vor, fuer "Buchung" schon', async () => {
      previewCsvColumnsMock.mockResolvedValue({
        columns: ['Buchung', 'Buchungsreferenz', 'Betrag'],
        detected_delimiter: ',',
        detected_encoding: 'utf-16',
        sample_rows: [],
      })
      const { container } = renderEditor()
      await uploadCsv(container)

      expect(suggestionFor('Buchung')).toBe('booking_date')
      expect(suggestionFor('Buchungsreferenz')).toBe('')
      expect(suggestionFor('Betrag')).toBe('amount')
    })

    it('laesst die uebrigen Partnerspalten unveraendert', async () => {
      const { container } = renderEditor()
      await uploadCsv(container)

      expect(suggestionFor('Partnername')).toBe('partner_name')
      expect(suggestionFor('Partner IBAN')).toBe('partner_iban')
      expect(suggestionFor('BIC/SWIFT')).toBe('partner_bic')
      expect(suggestionFor('Partner Kontonummer')).toBe('partner_account')
      expect(suggestionFor('Bankleitzahl')).toBe('partner_blz')
      expect(suggestionFor('Betrag')).toBe('amount')
      expect(suggestionFor('Währung')).toBe('currency')
    })

    it('meldet nur noch das fehlende Valutadatum, nicht mehr den fehlenden Verwendungszweck', async () => {
      const { container } = renderEditor()
      await uploadCsv(container)

      // Alle Spalten haben einen Vorschlag, es bleibt nur das echte Problem uebrig:
      // die Datei hat keine Valutadatum-Spalte.
      expect(screen.queryByText(/noch nicht zugeordnet/)).not.toBeInTheDocument()
      expect(await screen.findByText(/Pflichtfeld ohne Spalte: Valutadatum/)).toBeInTheDocument()
    })
  })
})
