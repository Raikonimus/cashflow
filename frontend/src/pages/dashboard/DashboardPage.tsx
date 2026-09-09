import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getAccountBalances, getLiquidity } from '@/api/journal'
import type { AccountBalanceRow, AccountBalanceTotal } from '@/api/journal'
import { useAuthStore } from '@/store/auth-store'
import { ScenarioSelect } from '@/components/ScenarioSelect'
import type { Scenario } from '@/api/forecast'
import { LiquidityChart } from './LiquidityChart'

function formatMoney(value: string, currency: string): string {
  const numeric = Number.parseFloat(value)
  const safe = Number.isNaN(numeric) ? 0 : numeric
  const formatted = safe.toLocaleString('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return `${formatted} ${currency === 'EUR' ? '\u20ac' : currency}`
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const [year, month, day] = value.split('-')
  if (!year || !month || !day) return value
  return `${day}.${month}.${year}`
}

function amountClass(value: string): string {
  return Number.parseFloat(value) < 0 ? 'text-red-600' : 'text-gray-900'
}

export function DashboardPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [scenario, setScenario] = useState<Scenario>('expected')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['account-balances', mandantId],
    queryFn: () => getAccountBalances(mandantId),
    enabled: !!mandantId,
  })

  const liquidityQuery = useQuery({
    queryKey: ['liquidity', mandantId, scenario],
    queryFn: () => getLiquidity(mandantId, scenario),
    enabled: !!mandantId,
  })

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center text-red-500">
        Fehler beim Laden der Kontostände.
      </div>
    )
  }

  const accounts = data?.accounts ?? []
  const totals = data?.totals ?? []

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Dashboard</h1>

      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-gray-800">Aktueller Kontostand</h2>
          <Link to="/accounts" className="text-sm text-blue-600 hover:underline">
            Konten verwalten
          </Link>
        </div>

        {accounts.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white px-4 py-6 text-center text-sm text-gray-400 shadow-sm">
            Noch keine Konten vorhanden.{' '}
            <Link to="/accounts/new" className="text-blue-600 hover:underline">
              Jetzt anlegen
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {totals.map((total: AccountBalanceTotal) => (
                <div
                  key={total.currency}
                  className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
                >
                  <p className="text-xs uppercase tracking-wide text-gray-400">
                    Gesamt {total.currency}
                    {totals.length > 1 ? ` · ${total.account_count} Konten` : ''}
                  </p>
                  <p
                    className={`mt-1 text-2xl font-semibold tabular-nums ${amountClass(total.current_balance)}`}
                  >
                    {formatMoney(total.current_balance, total.currency)}
                  </p>
                  <p className="mt-1 text-xs text-gray-500">
                    Startsaldo {formatMoney(total.opening_balance, total.currency)} + Buchungen{' '}
                    {formatMoney(total.booked_amount, total.currency)}
                  </p>
                </div>
              ))}
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Konto</th>
                    <th className="px-4 py-2 text-right font-medium">Startsaldo</th>
                    <th className="px-4 py-2 text-right font-medium">Buchungen</th>
                    <th className="px-4 py-2 text-right font-medium">Kontostand</th>
                    <th className="px-4 py-2 text-right font-medium">Stand vom</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {accounts.map((account: AccountBalanceRow) => (
                    <tr key={account.account_id}>
                      <td className="px-4 py-3">
                        <Link
                          to={`/accounts/${account.account_id}`}
                          className="font-medium text-gray-900 hover:underline"
                        >
                          {account.account_name}
                        </Link>
                        {account.foreign_currency_line_count > 0 ? (
                          <p className="text-xs text-amber-600">
                            {account.foreign_currency_line_count} Buchung
                            {account.foreign_currency_line_count === 1 ? '' : 'en'} in anderer
                            Währung nicht berücksichtigt
                          </p>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-500">
                        {formatMoney(account.opening_balance, account.currency)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-500">
                        {formatMoney(account.booked_amount, account.currency)}
                      </td>
                      <td
                        className={`px-4 py-3 text-right font-semibold tabular-nums ${amountClass(account.current_balance)}`}
                      >
                        {formatMoney(account.current_balance, account.currency)}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-500">
                        {formatDate(account.last_booking_date)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="mt-3 text-xs text-gray-500">
              Der Kontostand entspricht dem Startsaldo zuzüglich aller importierten Buchungen und
              gilt zum Datum der jeweils letzten Buchung. Den Startsaldo pflegst du in den
              Kontoeinstellungen.
            </p>
          </>
        )}
      </section>

      {accounts.length > 0 ? (
        <section className="mt-8">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-800">Liquiditätsvorschau</h2>
            <div className="flex items-center gap-3">
              <ScenarioSelect value={scenario} onChange={setScenario} />
              <Link to="/cashflow/forecast" className="text-sm text-blue-600 hover:underline">
                Prognoseregeln
              </Link>
            </div>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            {liquidityQuery.isLoading ? (
              <p className="text-sm text-gray-400">Prognose wird berechnet …</p>
            ) : liquidityQuery.isError || !liquidityQuery.data ? (
              <p className="text-sm text-red-500">Fehler beim Laden der Liquiditätsvorschau.</p>
            ) : (
              <LiquidityChart data={liquidityQuery.data} />
            )}
          </div>
        </section>
      ) : null}
    </div>
  )
}
