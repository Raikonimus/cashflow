/**
 * Ein- und Ausgabe von Geldbeträgen in Formularen.
 *
 * Akzeptiert deutsche ("1.234,56") wie englische ("1234.56") Schreibweise:
 * Enthält die Eingabe ein Komma, gilt es als Dezimaltrennzeichen und Punkte
 * sind Tausendertrennzeichen — sonst ist der Punkt das Dezimaltrennzeichen.
 */

const DECIMAL_PATTERN = /^-?\d+(\.\d{1,2})?$/

/** Normalisiert eine Eingabe zu "1234.56"; `null`, wenn sie kein Betrag ist. */
export function parseAmountInput(raw: string): string | null {
  const cleaned = raw.replace(/\s/g, '')
  if (cleaned === '') return '0.00'

  const normalized = cleaned.includes(',')
    ? cleaned.replace(/\./g, '').replace(',', '.')
    : cleaned
  if (!DECIMAL_PATTERN.test(normalized)) return null

  return Number.parseFloat(normalized).toFixed(2)
}

/** Stellt einen gespeicherten Betrag für das Eingabefeld dar ("1234.56" → "1234,56"). */
export function formatAmountInput(value: string | undefined | null): string {
  if (value === undefined || value === null || value === '') return '0,00'
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) return '0,00'
  return numeric.toFixed(2).replace('.', ',')
}
