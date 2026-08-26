import type ExcelJS from 'exceljs'
import { buildIncomeExpenseWorkbook, columnLetter } from './income-expense-excel'
import type { ExcelSheet, IncomeExpenseWorkbookInput } from './income-expense-excel'

const YEAR_COLUMNS = [
  { key: 'year_total', label: 'Jahr' },
  { key: 'jan', label: 'Jan' },
  { key: 'feb', label: 'Feb' },
]

function makeSheet(overrides: Partial<ExcelSheet> = {}): ExcelSheet {
  return {
    name: 'Einnahmen',
    currency: 'EUR',
    columns: YEAR_COLUMNS,
    excludedCurrencyCount: 0,
    excludedCurrencyAmountGross: '0.00',
    groups: [
      {
        name: 'Kunden',
        collapsed: false,
        services: [
          { label: 'Beispiel GmbH / Premium', values: ['300.00', '100.00', '200.00'] },
          { label: 'Beispiel GmbH / Beratung', values: ['50.00', '50.00', '0.00'] },
        ],
      },
      {
        name: 'Förderungen',
        collapsed: false,
        services: [{ label: 'AWS / Zuschuss', values: ['10.50', '10.50', '0.00'] }],
      },
    ],
    ...overrides,
  }
}

function makeInput(sheets: ExcelSheet[]): IncomeExpenseWorkbookInput {
  return { subtitle: 'Jahresansicht 2026', sheets }
}

function formulaOf(worksheet: ExcelJS.Worksheet, address: string): string {
  const value = worksheet.getCell(address).value as ExcelJS.CellFormulaValue
  return value.formula
}

describe('buildIncomeExpenseWorkbook', () => {
  it('legt je Sektion ein Tabellenblatt an', () => {
    const workbook = buildIncomeExpenseWorkbook(
      makeInput([
        makeSheet({ name: 'Einnahmen' }),
        makeSheet({ name: 'Ausgaben' }),
        makeSheet({ name: 'Erfolgsneutrale Zahlungen' }),
      ]),
    )

    expect(workbook.worksheets.map((sheet) => sheet.name)).toEqual([
      'Einnahmen',
      'Ausgaben',
      'Erfolgsneutrale Zahlungen',
    ])
  })

  it('schreibt Titel, Untertitel und Spaltenkoepfe', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet()]))
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('A1').value).toBe('Einnahmen')
    expect(worksheet.getCell('A2').value).toBe('Jahresansicht 2026 · Alle Angaben in EUR (netto)')
    expect(worksheet.getCell('A4').value).toBe('Leistung / Gruppe')
    expect(worksheet.getCell('B4').value).toBe('Jahr')
    expect(worksheet.getCell('C4').value).toBe('Jan')
    expect(worksheet.getCell('D4').value).toBe('Feb')
  })

  it('schreibt Gruppen ueber ihren Leistungen und darunter die Gesamtsumme', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet()]))
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('A5').value).toBe('Kunden')
    expect(worksheet.getCell('A6').value).toBe('Beispiel GmbH / Premium')
    expect(worksheet.getCell('A7').value).toBe('Beispiel GmbH / Beratung')
    expect(worksheet.getCell('A8').value).toBe('Förderungen')
    expect(worksheet.getCell('A9').value).toBe('AWS / Zuschuss')
    expect(worksheet.getCell('A10').value).toBe('Gesamtsumme')
  })

  it('schreibt Periodenwerte als Zahlen, nicht als Text', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet()]))
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('C6').value).toBe(100)
    expect(worksheet.getCell('D6').value).toBe(200)
    expect(worksheet.getCell('C9').value).toBe(10.5)
    expect(worksheet.getCell('C6').numFmt).toBe('#,##0.00')
  })

  it('berechnet die Total-Spalte einer Leistung per Formel aus den Periodenspalten', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet()]))
    const worksheet = workbook.worksheets[0]

    expect(formulaOf(worksheet, 'B6')).toBe('SUM(C6:D6)')
    expect(formulaOf(worksheet, 'B7')).toBe('SUM(C7:D7)')
  })

  it('berechnet die Gruppensumme per Formel aus ihren Leistungszeilen', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet()]))
    const worksheet = workbook.worksheets[0]

    expect(formulaOf(worksheet, 'B5')).toBe('SUM(B6:B7)')
    expect(formulaOf(worksheet, 'C5')).toBe('SUM(C6:C7)')
    expect(formulaOf(worksheet, 'D5')).toBe('SUM(D6:D7)')
    expect(formulaOf(worksheet, 'C8')).toBe('SUM(C9:C9)')
  })

  it('berechnet die Gesamtsumme per Formel aus den Gruppenzeilen', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet()]))
    const worksheet = workbook.worksheets[0]

    expect(formulaOf(worksheet, 'B10')).toBe('SUM(B5,B8)')
    expect(formulaOf(worksheet, 'C10')).toBe('SUM(C5,C8)')
    expect(formulaOf(worksheet, 'D10')).toBe('SUM(D5,D8)')
  })

  it('setzt eine leere Gruppe auf 0 statt auf eine kaputte Formel', () => {
    const workbook = buildIncomeExpenseWorkbook(
      makeInput([makeSheet({ groups: [{ name: 'Leere Gruppe', collapsed: false, services: [] }] })]),
    )
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('B5').value).toBe(0)
    expect(formulaOf(worksheet, 'B6')).toBe('SUM(B5)')
  })

  it('setzt die Gesamtsumme auf 0, wenn es keine Gruppen gibt', () => {
    const workbook = buildIncomeExpenseWorkbook(makeInput([makeSheet({ groups: [] })]))
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('A5').value).toBe('Gesamtsumme')
    expect(worksheet.getCell('B5').value).toBe(0)
  })

  it('bildet Gruppen als Excel-Gliederung ab und uebernimmt den Zuklapp-Zustand', () => {
    const workbook = buildIncomeExpenseWorkbook(
      makeInput([
        makeSheet({
          groups: [
            {
              name: 'Kunden',
              collapsed: true,
              services: [{ label: 'Beispiel GmbH', values: ['1.00', '1.00', '0.00'] }],
            },
            {
              name: 'Förderungen',
              collapsed: false,
              services: [{ label: 'AWS', values: ['2.00', '2.00', '0.00'] }],
            },
          ],
        }),
      ]),
    )
    const worksheet = workbook.worksheets[0]

    expect(worksheet.properties.outlineProperties?.summaryBelow).toBe(false)
    expect(worksheet.getRow(5).outlineLevel).toBe(0)
    expect(worksheet.getRow(6).outlineLevel).toBe(1)
    expect(worksheet.getRow(6).hidden).toBe(true)
    expect(worksheet.getRow(8).outlineLevel).toBe(1)
    expect(worksheet.getRow(8).hidden).toBe(false)
  })

  it('verarbeitet die Mehrjahresansicht mit einer Spalte je Jahr', () => {
    const workbook = buildIncomeExpenseWorkbook(
      makeInput([
        makeSheet({
          columns: [
            { key: 'total', label: 'Gesamt' },
            { key: '2024', label: '2024' },
            { key: '2025', label: '2025' },
            { key: '2026', label: '2026' },
          ],
          groups: [
            {
              name: 'Kunden',
              collapsed: false,
              services: [{ label: 'Beispiel GmbH', values: ['60.00', '10.00', '20.00', '30.00'] }],
            },
          ],
        }),
      ]),
    )
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('E4').value).toBe('2026')
    expect(formulaOf(worksheet, 'B6')).toBe('SUM(C6:E6)')
    expect(formulaOf(worksheet, 'E5')).toBe('SUM(E6:E6)')
    expect(formulaOf(worksheet, 'E7')).toBe('SUM(E5)')
  })

  it('ergaenzt den Hinweis auf ausgeschlossene Fremdwaehrungen nur bei Bedarf', () => {
    const withoutNote = buildIncomeExpenseWorkbook(makeInput([makeSheet()])).worksheets[0]
    expect(withoutNote.getCell('A12').value).toBeNull()

    const withNote = buildIncomeExpenseWorkbook(
      makeInput([makeSheet({ excludedCurrencyCount: 2, excludedCurrencyAmountGross: '1234.50' })]),
    ).worksheets[0]
    expect(String(withNote.getCell('A12').value)).toContain('Ausgeschlossene Fremdwährungen: 2')
  })

  it('behandelt unlesbare Betraege als 0', () => {
    const workbook = buildIncomeExpenseWorkbook(
      makeInput([
        makeSheet({
          groups: [
            {
              name: 'Kunden',
              collapsed: false,
              services: [{ label: 'Kaputt', values: ['', 'keine Zahl', ''] }],
            },
          ],
        }),
      ]),
    )
    const worksheet = workbook.worksheets[0]

    expect(worksheet.getCell('C6').value).toBe(0)
    expect(worksheet.getCell('D6').value).toBe(0)
  })
})

describe('columnLetter', () => {
  it('rechnet Spaltenindizes in Excel-Buchstaben um', () => {
    expect(columnLetter(1)).toBe('A')
    expect(columnLetter(26)).toBe('Z')
    expect(columnLetter(27)).toBe('AA')
    expect(columnLetter(28)).toBe('AB')
    expect(columnLetter(52)).toBe('AZ')
    expect(columnLetter(53)).toBe('BA')
  })
})
