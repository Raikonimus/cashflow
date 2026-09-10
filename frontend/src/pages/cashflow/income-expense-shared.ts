/** Was Matrix und Saldo-Leiste teilen müssen, damit sie untereinander passen.
 *
 *  Die Leiste steht direkt über den Tabellen und benutzt dieselben Spalten. Zwei Stellen
 *  mit demselben `w-[6.5rem]` wären ein Zwilling: Wer eine Breite ändert, verschiebt die
 *  Leiste gegen die Matrix, ohne dass ein Test das merkt.
 */

export const LABEL_COLUMN_WIDTH_CLASS = 'w-[26rem]'
export const VALUE_COLUMN_WIDTH_CLASS = 'w-[6.5rem]'
export const TABLE_CLASS = 'w-full min-w-[1200px] table-fixed text-sm'

/** Prognosewerte sind grau und kursiv — die Grenze zum Ist bleibt so sichtbar. */
export const FORECAST_CELL_CLASS = 'italic text-gray-400'

export function formatMoney(value: string, currency: string): string {
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) {
    return currency === 'EUR' ? '0' : `0 ${currency}`
  }
  const formatted = numeric.toLocaleString('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
  return currency === 'EUR' ? formatted : `${formatted} ${currency}`
}

/** Wie formatMoney, aber immer mit Währung — für Fließtext, über dem keine
 *  Spaltenüberschrift die Einheit trägt. Das Anhängen gehört hierher und nicht an die
 *  Aufrufstelle: formatMoney setzt bei Fremdwährung bereits den Code, ein zweites
 *  Zeichen daneben ergäbe "1.000 CHF €".
 */
export function formatMoneyWithCurrency(value: string, currency: string): string {
  const formatted = formatMoney(value, currency)
  return currency === 'EUR' ? `${formatted} €` : formatted
}
