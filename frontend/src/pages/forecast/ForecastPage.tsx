import { Fragment, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getForecastOverview } from '@/api/forecast'
import type { ForecastMode, ForecastServiceOverviewRow } from '@/api/forecast'
import { useAuthStore } from '@/store/auth-store'
import { ForecastRuleEditor } from './ForecastRuleEditor'
import { ForecastSnapshots } from './ForecastSnapshots'
import {
  CONFIDENCE_LABELS,
  HAND_SET_CLASS,
  RULE_LABELS_SHORT,
  accuracyClass,
  formatAccuracy,
  formatAdjustment,
} from './labels'

const EDIT_ROLES = new Set(['accountant', 'mandant_admin', 'admin'])

const MODE_BADGES: Record<ForecastMode, { label: string; title: string } | null> = {
  auto: null,
  manual: { label: 'händisch', title: 'Regeltyp von Hand gesetzt' },
  off: { label: 'aus', title: 'Prognose von Hand abgeschaltet' },
}

const CONFIDENCE_CLASSES: Record<string, string> = {
  high: 'bg-green-100 text-green-800',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-gray-200 text-gray-700',
}

type RowFilter = 'all' | 'customised' | 'without_rule' | 'weak' | 'stopped'

const FILTER_LABELS: Record<RowFilter, string> = {
  all: 'Alle Leistungen',
  customised: 'Von Hand angepasst',
  without_rule: 'Ohne Prognose',
  weak: 'Prognose trifft schlecht',
  stopped: 'Im Rückvergleich beendet',
}

const SECTION_LABELS: Record<string, string> = {
  income: 'Einnahme',
  expense: 'Ausgabe',
  neutral: 'Neutral',
}

function formatMoney(value: string): string {
  const numeric = Number.parseFloat(value)
  const safe = Number.isNaN(numeric) ? 0 : numeric
  return `${safe.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €`
}

export function ForecastPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const role = useAuthStore((s) => s.user?.role ?? '')
  const canEdit = EDIT_ROLES.has(role)

  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<RowFilter>('all')
  const expandedId = searchParams.get('service')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['forecast-overview', mandantId, search, filter],
    queryFn: () =>
      getForecastOverview(mandantId, {
        search,
        onlyWithoutRule: filter === 'without_rule',
      }),
    enabled: !!mandantId,
  })

  // "schwach" und "beendet" sind Eigenschaften der Messung, keine Serverabfrage —
  // die Zeilen sind ohnehin schon da.
  const rows = (data?.services ?? []).filter((row) => {
    if (filter === 'customised') return row.customised
    if (filter === 'weak') return row.backtest_ran && !row.beats_baseline && !row.service_stopped
    if (filter === 'stopped') return row.service_stopped
    return true
  })

  function toggleRow(serviceId: string) {
    const next = new URLSearchParams(searchParams)
    if (expandedId === serviceId) {
      next.delete('service')
    } else {
      next.set('service', serviceId)
    }
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-bold text-gray-900">Prognoseregeln</h1>
        <Link to="/cashflow/income-expense" className="text-sm text-blue-600 hover:underline">
          Zur Einnahmen-/Ausgabenmatrix
        </Link>
      </div>
      <p className="mb-6 text-sm text-gray-500">
        Für jede Leistung wird automatisch eine Regel aus der Historie abgeleitet. Hier siehst du,
        welche das ist — und kannst sie überschreiben, abschalten oder um bekannte Planposten
        ergänzen.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Leistung oder Partner suchen"
          aria-label="Leistung oder Partner suchen"
          className="w-64 rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as RowFilter)}
          aria-label="Auswahl einschränken"
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          {(Object.keys(FILTER_LABELS) as RowFilter[]).map((key) => (
            <option key={key} value={key}>
              {FILTER_LABELS[key]}
            </option>
          ))}
        </select>
        {data && (
          <span className="ml-auto text-sm text-gray-500">
            {rows.length} von {data.total} Leistungen
            {data.customised > 0 ? (
              <>
                {' · '}
                <button
                  type="button"
                  onClick={() => setFilter('customised')}
                  className={`rounded px-1.5 py-0.5 text-xs font-medium ${HAND_SET_CLASS}`}
                >
                  {data.customised} angepasst
                </button>
              </>
            ) : null}
          </span>
        )}
      </div>

      {data && data.backtested > 0 && (
        <dl className="mb-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-gray-200 bg-gray-200 text-sm sm:grid-cols-4">
          <div className="bg-white px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-gray-400">Rückverglichen</dt>
            <dd className="text-lg font-semibold tabular-nums text-gray-900">
              {data.backtested}
              <span className="ml-1 text-xs font-normal text-gray-400">von {data.total}</span>
            </dd>
          </div>
          <div className="bg-white px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-gray-400">
              Typischer Fehler
            </dt>
            <dd className="text-lg font-semibold tabular-nums text-gray-900">
              {formatAccuracy(data.median_relative_error) ?? '—'}
            </dd>
          </div>
          <div className="bg-white px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-gray-400">Regel gewechselt</dt>
            <dd className="text-lg font-semibold tabular-nums text-gray-900">
              {data.replaced_by_backtest}
            </dd>
          </div>
          <div className="bg-white px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-gray-400">Beendet erkannt</dt>
            <dd className="text-lg font-semibold tabular-nums text-gray-900">
              {data.stopped_by_backtest}
            </dd>
          </div>
        </dl>
      )}

      {data && data.weak_forecasts > 0 && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          Bei {data.weak_forecasts}{' '}
          {data.weak_forecasts === 1 ? 'Leistung trifft' : 'Leistungen trifft'} die Regel
          schlechter als gar keine Prognose. Dort hilft ein Planposten oder das Abschalten
          mehr als eine Schätzung.{' '}
          <button
            type="button"
            onClick={() => setFilter('weak')}
            className="font-medium underline underline-offset-2"
          >
            Anzeigen
          </button>
        </p>
      )}

      {isLoading && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-8 text-center text-gray-500">
          Regeln werden geladen …
        </div>
      )}
      {isError && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-8 text-center text-red-500">
          Fehler beim Laden der Prognoseregeln.
        </div>
      )}

      {data && !isLoading && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          {rows.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-gray-400">
              Keine Leistungen gefunden.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Leistung</th>
                  <th className="px-3 py-2 text-left font-medium">Regel</th>
                  <th className="px-3 py-2 text-left font-medium">Güte</th>
                  <th className="px-3 py-2 text-right font-medium">Nächste 12 Monate</th>
                  <th className="px-3 py-2 text-right font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((row: ForecastServiceOverviewRow) => {
                  const badge = MODE_BADGES[row.mode]
                  const adjustment = formatAdjustment(row.adjustment_pct)
                  const isExpanded = expandedId === row.service_id
                  return (
                    <Fragment key={row.service_id}>
                      <tr className={isExpanded ? 'bg-blue-50/40' : undefined}>
                        <td className="px-4 py-2">
                          <div className="font-medium text-gray-900">{row.service_name}</div>
                          <div className="text-xs text-gray-500">
                            {row.partner_name ?? '—'} · {SECTION_LABELS[row.section] ?? row.section}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-gray-700">
                            {RULE_LABELS_SHORT[row.effective_rule_type] ?? row.effective_rule_type}
                          </span>
                          {badge && (
                            <span
                              title={badge.title}
                              className={`ml-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium ${HAND_SET_CLASS}`}
                            >
                              {badge.label}
                            </span>
                          )}
                          {adjustment && (
                            <span
                              title="Prozentuale Anpassung von Hand"
                              className={`ml-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium tabular-nums ${HAND_SET_CLASS}`}
                            >
                              {adjustment}
                            </span>
                          )}
                          {row.shift_months > 0 && (
                            <span
                              title="Zahlungsverzug von Hand gesetzt"
                              className={`ml-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium ${HAND_SET_CLASS}`}
                            >
                              +{row.shift_months} Mon.
                            </span>
                          )}
                          {row.planned_item_count > 0 && (
                            <span
                              title="Händische Planposten"
                              className={`ml-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium ${HAND_SET_CLASS}`}
                            >
                              {row.planned_item_count} Planposten
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {row.relative_error !== null ? (
                            <span
                              title="Im Rückvergleich gemessener mittlerer Fehler"
                              className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${accuracyClass(
                                row.relative_error,
                              )}`}
                            >
                              {formatAccuracy(row.relative_error)}
                            </span>
                          ) : row.confidence ? (
                            <span
                              title="Geschätzt — für einen Rückvergleich fehlt die Historie"
                              className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                                CONFIDENCE_CLASSES[row.confidence] ?? ''
                              }`}
                            >
                              {CONFIDENCE_LABELS[row.confidence] ?? row.confidence}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400">—</span>
                          )}
                          {row.service_stopped && (
                            <span className="ml-1 rounded bg-gray-200 px-1.5 py-0.5 text-[11px] font-medium text-gray-600">
                              beendet
                            </span>
                          )}
                          {row.backtest_ran && !row.beats_baseline && !row.service_stopped && (
                            <span className="ml-1 rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-700">
                              schwach
                            </span>
                          )}
                        </td>
                        <td
                          className={`px-3 py-2 text-right tabular-nums ${
                            Number.parseFloat(row.next_12_months) < 0
                              ? 'text-red-600'
                              : 'text-gray-900'
                          }`}
                        >
                          {formatMoney(row.next_12_months)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            onClick={() => toggleRow(row.service_id)}
                            aria-expanded={isExpanded}
                            className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50"
                          >
                            {isExpanded ? 'Schließen' : 'Regel bearbeiten'}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={5} className="p-0">
                            <ForecastRuleEditor
                              mandantId={mandantId}
                              serviceId={row.service_id}
                              canEdit={canEdit}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      <ForecastSnapshots mandantId={mandantId} canEdit={canEdit} />
    </div>
  )
}
