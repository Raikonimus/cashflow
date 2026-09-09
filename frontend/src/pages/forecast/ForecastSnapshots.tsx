import { Fragment, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createSnapshot, deleteSnapshot, getSnapshot, listSnapshots } from '@/api/forecast'
import type { SnapshotSummary } from '@/api/forecast'
import { formatPeriod } from './labels'

function money(value: string | null): string {
  if (value === null) return '—'
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) return '—'
  return `${numeric.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €`
}

function deviationClass(value: string | null): string {
  if (value === null) return 'text-gray-400'
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) return 'text-gray-400'
  return numeric < 0 ? 'text-red-600' : 'text-green-700'
}

function formatDate(iso: string): string {
  const [year, month, day] = iso.split('-')
  return year && month && day ? `${day}.${month}.${year}` : iso
}

function SnapshotDetailTable({ mandantId, snapshotId }: { mandantId: string; snapshotId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['forecast-snapshot', mandantId, snapshotId],
    queryFn: () => getSnapshot(mandantId, snapshotId),
  })

  if (isLoading) return <p className="px-4 py-3 text-sm text-gray-400">Wird geladen …</p>
  if (!data) return null

  return (
    <div className="border-t border-gray-200 bg-gray-50 px-4 py-3">
      {data.elapsed_months === 0 ? (
        <p className="mb-3 text-sm text-gray-500">
          Noch kein Monat vollständig abgelaufen — es gibt nichts zu vergleichen.
        </p>
      ) : (
        <p className="mb-3 text-sm text-gray-600">
          Über {data.elapsed_months}{' '}
          {data.elapsed_months === 1 ? 'abgelaufenen Monat' : 'abgelaufene Monate'} weicht der Saldo
          im Mittel um{' '}
          <span className="font-medium tabular-nums">{money(data.mean_absolute_deviation)}</span>{' '}
          vom Plan ab.
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium">Monat</th>
              <th className="px-2 py-1.5 text-right font-medium">Plan</th>
              <th className="px-2 py-1.5 text-right font-medium">Ist</th>
              <th className="px-2 py-1.5 text-right font-medium">Monat ±</th>
              <th className="px-2 py-1.5 text-right font-medium">Plan-Saldo</th>
              <th className="px-2 py-1.5 text-right font-medium">Ist-Saldo</th>
              <th className="px-2 py-1.5 text-right font-medium">Saldo ±</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {data.months.map((month) => (
              <tr key={month.period} className={month.actual_net === null ? 'text-gray-400' : ''}>
                <td className="px-2 py-1.5">
                  {formatPeriod(month.period)}
                  {month.actual_net !== null && !month.is_complete ? (
                    <span className="ml-1 text-[10px] text-gray-400">(läuft)</span>
                  ) : null}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{money(month.planned_net)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{money(month.actual_net)}</td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${deviationClass(month.net_deviation)}`}
                >
                  {money(month.net_deviation)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {money(month.planned_closing)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {money(month.actual_closing)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right font-medium tabular-nums ${deviationClass(month.deviation)}`}
                >
                  {money(month.deviation)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ForecastSnapshots({ mandantId, canEdit }: { mandantId: string; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [openId, setOpenId] = useState<string | null>(null)
  const [label, setLabel] = useState('')

  const { data: snapshots } = useQuery({
    queryKey: ['forecast-snapshots', mandantId],
    queryFn: () => listSnapshots(mandantId),
    enabled: !!mandantId,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['forecast-snapshots', mandantId] })
  }

  const create = useMutation({
    mutationFn: () => createSnapshot(mandantId, { label: label.trim() || null }),
    onSuccess: (snapshot) => {
      setLabel('')
      setOpenId(snapshot.id)
      invalidate()
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSnapshot(mandantId, id),
    onSuccess: () => {
      setOpenId(null)
      invalidate()
    },
  })

  return (
    <section className="mt-10">
      <h2 className="mb-1 text-lg font-semibold text-gray-900">Plan gegen Ist</h2>
      <p className="mb-4 text-sm text-gray-500">
        Ein Planstand friert die heutige Liquiditätskurve ein. Sobald Monate ablaufen, steht
        daneben, was tatsächlich geflossen ist — verglichen wird gegen alle Kontobewegungen, nicht
        nur gegen die prognostizierten Leistungen.
      </p>

      {canEdit && (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate()
          }}
          className="mb-4 flex flex-wrap items-center gap-2"
        >
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Bezeichnung, z. B. Vor der Budgetrunde"
            aria-label="Bezeichnung des Planstands"
            className="w-72 rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Planstand festhalten
          </button>
          {create.isError && (
            <span className="text-sm text-red-500">Planstand konnte nicht angelegt werden.</span>
          )}
        </form>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {!snapshots || snapshots.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-gray-400">
            Noch kein Planstand festgehalten.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Planstand</th>
                <th className="px-3 py-2 text-left font-medium">Stichtag</th>
                <th className="px-3 py-2 text-right font-medium">Abgelaufen</th>
                <th className="px-3 py-2 text-right font-medium">Saldo-Abweichung</th>
                <th className="px-3 py-2 text-right font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {snapshots.map((snapshot: SnapshotSummary) => {
                const isOpen = openId === snapshot.id
                return (
                  <Fragment key={snapshot.id}>
                    <tr className={isOpen ? 'bg-blue-50/40' : undefined}>
                      <td className="px-4 py-2">
                        <div className="font-medium text-gray-900">
                          {snapshot.label ?? 'Ohne Bezeichnung'}
                        </div>
                        <div className="text-xs text-gray-500">
                          {snapshot.month_count} Monate
                          {snapshot.scenario !== 'expected'
                            ? ` · Szenario ${snapshot.scenario}`
                            : ''}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-gray-600">{formatDate(snapshot.as_of)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                        {snapshot.elapsed_months}
                      </td>
                      <td
                        className={`px-3 py-2 text-right tabular-nums ${deviationClass(snapshot.latest_deviation)}`}
                      >
                        {money(snapshot.latest_deviation)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => setOpenId(isOpen ? null : snapshot.id)}
                          aria-expanded={isOpen}
                          className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50"
                        >
                          {isOpen ? 'Schließen' : 'Vergleich'}
                        </button>
                        {canEdit && (
                          <button
                            type="button"
                            onClick={() => remove.mutate(snapshot.id)}
                            className="ml-2 rounded border border-gray-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                          >
                            Löschen
                          </button>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={5} className="p-0">
                          <SnapshotDetailTable mandantId={mandantId} snapshotId={snapshot.id} />
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
    </section>
  )
}
