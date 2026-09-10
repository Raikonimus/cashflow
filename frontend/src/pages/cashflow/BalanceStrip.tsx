import { useSyncedScrollRef } from './synced-scroll'
import {
  FORECAST_CELL_CLASS,
  LABEL_COLUMN_WIDTH_CLASS,
  TABLE_CLASS,
  VALUE_COLUMN_WIDTH_CLASS,
  formatMoney,
  formatMoneyWithCurrency,
} from './income-expense-shared'

export interface BalanceStripColumn {
  key: string
  label: string
  /** Kontostand am Ende dieser Periode; null, wenn dafür nichts vorliegt. */
  balance: string | null
  isForecast: boolean
}

/** Farbe einer Zelle. Wird in einem Zug entschieden, weil sich zwei Tailwind-Klassen
 *  für dieselbe Eigenschaft sonst je nach Reihenfolge im Stylesheet überstimmen — und
 *  ein überschriebenes Rot wäre genau die Warnung, die niemand sieht. */
function toneFor(balance: string | null, isForecast: boolean): string {
  const isNegative = balance !== null && Number.parseFloat(balance) < 0
  if (isForecast) {
    return isNegative ? 'italic text-red-400' : FORECAST_CELL_CLASS
  }
  return isNegative ? 'text-red-700' : ''
}

function formatAsOf(asOf: string): string {
  const parsed = new Date(asOf)
  if (Number.isNaN(parsed.getTime())) {
    return asOf
  }
  return parsed.toLocaleDateString('de-DE')
}

/** Der Bestand über den Flüssen: was am Ende jeder Periode auf den Konten steht.
 *
 *  Die Matrix darunter zeigt, was in einem Monat hereinkommt und hinausgeht. Diese Leiste
 *  zeigt, wo das Konto danach steht — dieselben Spalten, dieselbe Grenze zwischen Ist und
 *  Prognose.
 */
export function BalanceStrip({
  title,
  columns,
  currency,
  openingBalance,
  openingLabel,
  asOf,
  isLoading = false,
  isError = false,
}: Readonly<{
  title: string
  columns: BalanceStripColumn[]
  currency: string
  openingBalance: string | null
  openingLabel: string
  asOf: string | null
  isLoading?: boolean
  isError?: boolean
}>) {
  const hasForecast = columns.some((column) => column.isForecast)
  const scrollRef = useSyncedScrollRef<HTMLDivElement>()

  return (
    <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-3">
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        <div className="flex flex-wrap items-baseline gap-3 text-xs text-gray-500">
          {openingBalance !== null && (
            <span>
              {openingLabel}: {formatMoneyWithCurrency(openingBalance, currency)}
            </span>
          )}
          {asOf && <span>Buchungen bis {formatAsOf(asOf)}</span>}
          {hasForecast && (
            <span className={`${FORECAST_CELL_CLASS} not-italic`}>Graue Werte: Prognose</span>
          )}
        </div>
      </header>

      {isError ? (
        <p className="px-4 py-3 text-sm text-red-700">Kontostand konnte nicht geladen werden.</p>
      ) : (
        <div ref={scrollRef} className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <caption className="sr-only">{title}</caption>
            <colgroup>
              <col className={LABEL_COLUMN_WIDTH_CLASS} />
              {columns.map((column) => (
                <col key={`balance-col-${column.key}`} className={VALUE_COLUMN_WIDTH_CLASS} />
              ))}
            </colgroup>
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 px-4 py-2 text-left">Periode</th>
                {columns.map((column, index) => (
                  <th
                    key={column.key}
                    className={`px-3 py-2 text-right ${index === 0 ? 'bg-amber-100 font-semibold text-amber-900' : ''} ${column.isForecast ? 'text-gray-400' : ''}`}
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="font-semibold text-gray-800">
                <th scope="row" className="sticky left-0 z-10 bg-white px-4 py-2 text-left">
                  Kontostand
                </th>
                {columns.map((column, index) => (
                  <td
                    key={column.key}
                    className={`px-3 py-2 text-right tabular-nums ${index === 0 ? 'bg-amber-50' : ''} ${toneFor(column.balance, column.isForecast)}`}
                    title={column.isForecast ? 'Prognostizierter Kontostand' : undefined}
                  >
                    {isLoading || column.balance === null
                      ? '–'
                      : formatMoney(column.balance, currency)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
