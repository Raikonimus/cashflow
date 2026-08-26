import ExcelJS from 'exceljs'

/**
 * Excel-Export der Einnahmen-&-Ausgaben-Matrix.
 *
 * Die Summen werden nicht als Werte geschrieben, sondern als echte Excel-Formeln:
 * Gruppensummen summieren ihre Leistungszeilen, die Gesamtsumme summiert die
 * Gruppenzeilen, und die Total-Spalte summiert die Periodenspalten der jeweiligen
 * Zeile. Damit rechnet die Datei nach jeder Aenderung selbst weiter.
 */

const LABEL_COLUMN = 1
const FIRST_VALUE_COLUMN = 2
const TITLE_ROW = 1
const SUBTITLE_ROW = 2
const HEADER_ROW = 4
const FIRST_DATA_ROW = HEADER_ROW + 1
const NUMBER_FORMAT = '#,##0.00'

const HEADER_FILL = 'FFF3F4F6'
const GROUP_FILL = 'FFF9FAFB'
const TOTAL_FILL = 'FFE5E7EB'
const ACCENT_FILL = 'FFFEF3C7'
const BORDER_COLOR = 'FFD1D5DB'
const MUTED_COLOR = 'FF6B7280'

export interface ExcelPeriodColumn {
  key: string
  label: string
}

export interface ExcelServiceRow {
  label: string
  /** Werte in Spaltenreihenfolge; Index 0 ist die Total-Spalte und wird durch eine Formel ersetzt. */
  values: string[]
}

export interface ExcelGroupRow {
  name: string
  collapsed: boolean
  services: ExcelServiceRow[]
}

export interface ExcelSheet {
  name: string
  currency: string
  columns: ExcelPeriodColumn[]
  groups: ExcelGroupRow[]
  excludedCurrencyCount: number
  excludedCurrencyAmountGross: string
}

export interface IncomeExpenseWorkbookInput {
  subtitle: string
  sheets: ExcelSheet[]
}

export function columnLetter(index: number): string {
  let remaining = index
  let letters = ''
  while (remaining > 0) {
    const rest = (remaining - 1) % 26
    letters = String.fromCodePoint(65 + rest) + letters
    remaining = Math.floor((remaining - rest - 1) / 26)
  }
  return letters
}

function parseAmount(value: string | undefined): number {
  const numeric = Number.parseFloat(value ?? '')
  return Number.isNaN(numeric) ? 0 : numeric
}

function formula(expression: string): ExcelJS.CellFormulaValue {
  return { formula: expression, date1904: false }
}

function applyFill(cell: ExcelJS.Cell, argb: string): void {
  cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb } }
}

/** Total-Spalte hebt sich wie in der UI ab, die uebrigen Spalten teilen sich eine Fuellung. */
function fillValueRow(row: ExcelJS.Row, lastColumn: number, defaultFill: string): void {
  for (let column = FIRST_VALUE_COLUMN; column <= lastColumn; column += 1) {
    applyFill(row.getCell(column), column === FIRST_VALUE_COLUMN ? ACCENT_FILL : defaultFill)
  }
}

function writeHeader(worksheet: ExcelJS.Worksheet, sheet: ExcelSheet, subtitle: string, lastColumn: number): void {
  worksheet.getColumn(LABEL_COLUMN).width = 46
  for (let column = FIRST_VALUE_COLUMN; column <= lastColumn; column += 1) {
    worksheet.getColumn(column).width = 14
  }

  const titleCell = worksheet.getCell(TITLE_ROW, LABEL_COLUMN)
  titleCell.value = sheet.name
  titleCell.font = { bold: true, size: 14 }

  const subtitleCell = worksheet.getCell(SUBTITLE_ROW, LABEL_COLUMN)
  subtitleCell.value = `${subtitle} · Alle Angaben in ${sheet.currency} (netto)`
  subtitleCell.font = { size: 10, color: { argb: MUTED_COLOR } }

  const headerRow = worksheet.getRow(HEADER_ROW)
  headerRow.getCell(LABEL_COLUMN).value = 'Leistung / Gruppe'
  sheet.columns.forEach((column, index) => {
    headerRow.getCell(FIRST_VALUE_COLUMN + index).value = column.label
  })
  headerRow.font = { bold: true }
  headerRow.alignment = { horizontal: 'right' }
  headerRow.getCell(LABEL_COLUMN).alignment = { horizontal: 'left' }
  applyFill(headerRow.getCell(LABEL_COLUMN), HEADER_FILL)
  fillValueRow(headerRow, lastColumn, HEADER_FILL)
  for (let column = LABEL_COLUMN; column <= lastColumn; column += 1) {
    headerRow.getCell(column).border = { bottom: { style: 'thin', color: { argb: BORDER_COLOR } } }
  }
}

function writeServiceRow(
  worksheet: ExcelJS.Worksheet,
  service: ExcelServiceRow,
  rowIndex: number,
  columnCount: number,
  lastColumn: number,
  collapsed: boolean,
): void {
  const row = worksheet.getRow(rowIndex)
  row.getCell(LABEL_COLUMN).value = service.label
  row.getCell(LABEL_COLUMN).alignment = { indent: 2 }

  // Total-Spalte summiert die Periodenspalten derselben Zeile.
  const firstPeriod = columnLetter(FIRST_VALUE_COLUMN + 1)
  const lastPeriod = columnLetter(lastColumn)
  row.getCell(FIRST_VALUE_COLUMN).value = formula(`SUM(${firstPeriod}${rowIndex}:${lastPeriod}${rowIndex})`)

  for (let offset = 1; offset < columnCount; offset += 1) {
    row.getCell(FIRST_VALUE_COLUMN + offset).value = parseAmount(service.values[offset])
  }
  for (let column = FIRST_VALUE_COLUMN; column <= lastColumn; column += 1) {
    row.getCell(column).numFmt = NUMBER_FORMAT
  }
  applyFill(row.getCell(FIRST_VALUE_COLUMN), ACCENT_FILL)

  // Leistungen haengen als Excel-Gliederungsebene unter ihrer Gruppe und
  // uebernehmen deren Zuklapp-Zustand aus der UI.
  row.outlineLevel = 1
  row.hidden = collapsed
}

function writeGroupRow(
  worksheet: ExcelJS.Worksheet,
  group: ExcelGroupRow,
  rowIndex: number,
  firstServiceRow: number,
  lastServiceRow: number,
  lastColumn: number,
): void {
  const row = worksheet.getRow(rowIndex)
  row.getCell(LABEL_COLUMN).value = group.name
  for (let column = FIRST_VALUE_COLUMN; column <= lastColumn; column += 1) {
    const letter = columnLetter(column)
    const cell = row.getCell(column)
    // Gruppensumme = Summe ihrer Leistungszeilen. Eine leere Gruppe bleibt bei 0.
    cell.value = group.services.length > 0
      ? formula(`SUM(${letter}${firstServiceRow}:${letter}${lastServiceRow})`)
      : 0
    cell.numFmt = NUMBER_FORMAT
  }
  applyFill(row.getCell(LABEL_COLUMN), GROUP_FILL)
  fillValueRow(row, lastColumn, GROUP_FILL)
  row.font = { bold: true }
}

function writeTotalRow(
  worksheet: ExcelJS.Worksheet,
  groupRowIndexes: number[],
  rowIndex: number,
  lastColumn: number,
): void {
  const row = worksheet.getRow(rowIndex)
  row.getCell(LABEL_COLUMN).value = 'Gesamtsumme'
  for (let column = FIRST_VALUE_COLUMN; column <= lastColumn; column += 1) {
    const letter = columnLetter(column)
    const cell = row.getCell(column)
    // Gesamtsumme = Summe der Gruppenzeilen. Die sind nicht zusammenhaengend,
    // daher einzeln referenziert statt als Bereich.
    const references = groupRowIndexes.map((groupRow) => letter + String(groupRow)).join(',')
    cell.value = references ? formula(`SUM(${references})`) : 0
    cell.numFmt = NUMBER_FORMAT
  }
  applyFill(row.getCell(LABEL_COLUMN), TOTAL_FILL)
  fillValueRow(row, lastColumn, TOTAL_FILL)
  for (let column = LABEL_COLUMN; column <= lastColumn; column += 1) {
    row.getCell(column).border = { top: { style: 'thin', color: { argb: BORDER_COLOR } } }
  }
  row.font = { bold: true }
}

function writeExcludedCurrencyNote(worksheet: ExcelJS.Worksheet, sheet: ExcelSheet, rowIndex: number): void {
  const amount = parseAmount(sheet.excludedCurrencyAmountGross)
  if (sheet.excludedCurrencyCount === 0 && Math.abs(amount) <= 0.0000001) {
    return
  }
  const formatted = amount.toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const cell = worksheet.getCell(rowIndex, LABEL_COLUMN)
  cell.value = `Ausgeschlossene Fremdwährungen: ${sheet.excludedCurrencyCount} (${formatted} ${sheet.currency})`
  cell.font = { size: 10, italic: true, color: { argb: MUTED_COLOR } }
}

function writeSheet(workbook: ExcelJS.Workbook, sheet: ExcelSheet, subtitle: string): void {
  const worksheet = workbook.addWorksheet(sheet.name, {
    views: [{ state: 'frozen', xSplit: LABEL_COLUMN, ySplit: HEADER_ROW }],
    properties: { outlineLevelRow: 1 },
  })
  // Die Gruppenzeile steht ueber ihren Leistungen, nicht darunter.
  worksheet.properties.outlineProperties = { summaryBelow: false, summaryRight: false }

  const lastColumn = FIRST_VALUE_COLUMN + sheet.columns.length - 1
  writeHeader(worksheet, sheet, subtitle, lastColumn)

  let rowIndex = FIRST_DATA_ROW
  const groupRowIndexes: number[] = []

  for (const group of sheet.groups) {
    const groupRowIndex = rowIndex
    groupRowIndexes.push(groupRowIndex)
    rowIndex += 1

    const firstServiceRow = rowIndex
    for (const service of group.services) {
      writeServiceRow(worksheet, service, rowIndex, sheet.columns.length, lastColumn, group.collapsed)
      rowIndex += 1
    }

    writeGroupRow(worksheet, group, groupRowIndex, firstServiceRow, rowIndex - 1, lastColumn)
  }

  writeTotalRow(worksheet, groupRowIndexes, rowIndex, lastColumn)
  writeExcludedCurrencyNote(worksheet, sheet, rowIndex + 2)
}

export function buildIncomeExpenseWorkbook(input: IncomeExpenseWorkbookInput): ExcelJS.Workbook {
  const workbook = new ExcelJS.Workbook()
  workbook.creator = 'CashFlow'
  for (const sheet of input.sheets) {
    writeSheet(workbook, sheet, input.subtitle)
  }
  return workbook
}

export async function downloadIncomeExpenseWorkbook(
  input: IncomeExpenseWorkbookInput,
  fileName: string,
): Promise<void> {
  const workbook = buildIncomeExpenseWorkbook(input)
  const buffer = await workbook.xlsx.writeBuffer()
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
