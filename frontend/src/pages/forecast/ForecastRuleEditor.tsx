import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createPlannedItem,
  deletePlannedItem,
  getForecastRule,
  listPlannedItems,
  resetForecastRule,
  setForecastRule,
} from '@/api/forecast'
import type { Backtest, ForecastMode, ForecastRule, ForecastRuleType } from '@/api/forecast'
import { extractErrorMessage } from '@/api/errors'
import { formatAmountInput, parseAmountInput } from '@/lib/amount-input'
import {
  CADENCE_LABELS,
  CANDIDATE_HINT,
  MODE_LABELS,
  MONTHS,
  plannedStatus,
  RULE_LABELS_LONG,
  SELECTABLE_RULES,
  accuracyClass,
  formatAccuracy,
  formatPeriod,
} from './labels'

function BacktestSection({ backtest }: { backtest: Backtest }) {
  const [open, setOpen] = useState(false)

  if (!backtest.ran) {
    return (
      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Rückvergleich
        </h4>
        <p className="text-xs text-gray-500">
          {backtest.reason}. Die Bandbreite dieser Leistung ist deshalb geschätzt, nicht
          gemessen.
        </p>
      </section>
    )
  }

  return (
    <section>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Rückvergleich
      </h4>
      <p className="text-gray-700">
        Geprüft an {backtest.holdout_months} Monaten
        {backtest.holdout_from && backtest.holdout_to
          ? ` (${formatPeriod(backtest.holdout_from)} – ${formatPeriod(backtest.holdout_to)})`
          : ''}
        {backtest.relative_error !== null ? (
          <>
            {' · '}
            <span
              className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${accuracyClass(backtest.relative_error)}`}
            >
              {formatAccuracy(backtest.relative_error)}
            </span>
          </>
        ) : null}
      </p>

      {backtest.service_stopped && (
        <p className="mt-1 text-xs text-gray-600">
          {backtest.reason}. Die Prognose ist damit abgeschaltet — falls die Leistung doch
          weiterläuft, hilft ein händischer Regeltyp oder ein Planposten.
        </p>
      )}
      {backtest.replaced_detected && (
        <p className="mt-1 text-xs text-gray-600">
          Der Rückvergleich hat eine andere Regel gewählt als das erkannte Muster.
        </p>
      )}
      {!backtest.beats_baseline && !backtest.service_stopped && (
        <p className="mt-1 text-xs text-red-700">
          Diese Regel trifft schlechter als gar keine Prognose. Ein Planposten oder
          „Keine Prognose" bildet die Realität hier ehrlicher ab.
        </p>
      )}

      {backtest.candidates.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-expanded={open}
            className="mt-1 text-xs text-blue-600 hover:underline"
          >
            {open ? 'Geprüfte Regeln ausblenden' : `Alle ${backtest.candidates.length} geprüften Regeln`}
          </button>
          {open && (
            <div className="mt-2">
              <p className="mb-1 text-xs text-gray-500">{CANDIDATE_HINT}</p>
              <table className="text-xs">
                <thead>
                  <tr className="text-gray-500">
                    <th className="px-2 py-1 text-left font-medium">Regel</th>
                    <th className="px-2 py-1 text-right font-medium">Score</th>
                    <th className="px-2 py-1 text-right font-medium">Ø Monatsfehler</th>
                    <th className="px-2 py-1 text-right font-medium">Summenfehler</th>
                  </tr>
                </thead>
                <tbody>
                  {backtest.candidates.map((candidate) => (
                    <tr
                      key={candidate.key}
                      className={
                        candidate.is_winner
                          ? 'font-semibold text-gray-900'
                          : candidate.is_baseline
                            ? 'italic text-gray-400'
                            : 'text-gray-600'
                      }
                    >
                      <td className="px-2 py-1">
                        {candidate.label}
                        {candidate.is_winner ? ' ✓' : ''}
                      </td>
                      <td className="px-2 py-1 text-right tabular-nums">
                        {formatMoney(candidate.score)}
                      </td>
                      <td className="px-2 py-1 text-right tabular-nums">
                        {formatMoney(candidate.mae)}
                      </td>
                      <td className="px-2 py-1 text-right tabular-nums">
                        {formatMoney(candidate.level_error)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}

interface FormState {
  mode: ForecastMode
  ruleType: ForecastRuleType
  amount: string
  intervalMonths: number
  anchorMonth: number
  windowMonths: number
  specialMonths: number[]
  specialFactor: string
  adjustmentPct: string
  shiftMonths: number
}

function toFormState(rule: ForecastRule): FormState {
  const params = rule.params ?? {}
  const special = params.special_months ?? {}
  const factors = Object.values(special)
  return {
    mode: rule.mode,
    ruleType: rule.rule_type ?? (rule.detected_rule_type === 'none' ? 'fixed_recurring' : rule.detected_rule_type),
    amount: formatAmountInput(params.amount ?? rule.median_amount),
    intervalMonths: params.interval_months ?? 1,
    anchorMonth: params.anchor_month ?? 1,
    windowMonths: params.window_months ?? 6,
    specialMonths: Object.keys(special).map((month) => Number.parseInt(month, 10)),
    specialFactor: factors.length > 0 ? String(factors[0]) : '2',
    adjustmentPct: rule.adjustment_pct,
    shiftMonths: rule.shift_months,
  }
}

function formatMoney(value: string): string {
  const numeric = Number.parseFloat(value)
  const safe = Number.isNaN(numeric) ? 0 : numeric
  return `${safe.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}

export function ForecastRuleEditor({
  mandantId,
  serviceId,
  canEdit,
}: {
  mandantId: string
  serviceId: string
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  // Der Serverstand ist die Quelle; `draft` liegt als Overlay darüber und wird nach
  // jedem erfolgreichen Schreiben verworfen. So braucht es kein setState im Effekt.
  const [draft, setDraft] = useState<FormState | null>(null)
  const [error, setError] = useState<string | null>(null)

  const ruleQuery = useQuery({
    queryKey: ['forecast-rule', mandantId, serviceId],
    queryFn: () => getForecastRule(mandantId, serviceId),
  })

  const plannedQuery = useQuery({
    queryKey: ['planned-items', mandantId, serviceId],
    queryFn: () => listPlannedItems(mandantId, serviceId),
  })

  function invalidateForecasts() {
    queryClient.invalidateQueries({ queryKey: ['forecast-rule', mandantId, serviceId] })
    queryClient.invalidateQueries({ queryKey: ['planned-items', mandantId, serviceId] })
    queryClient.invalidateQueries({ queryKey: ['forecast-overview', mandantId] })
    queryClient.invalidateQueries({ queryKey: ['income-expense-matrix'] })
    queryClient.invalidateQueries({ queryKey: ['income-expense-multi-matrix'] })
    queryClient.invalidateQueries({ queryKey: ['liquidity', mandantId] })
  }

  const serverForm = useMemo(
    () => (ruleQuery.data ? toFormState(ruleQuery.data) : null),
    [ruleQuery.data],
  )
  const form = draft ?? serverForm
  const setForm = setDraft

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!form) throw new Error('Formular nicht bereit')
      const params =
        form.mode !== 'manual'
          ? null
          : form.ruleType === 'fixed_recurring'
            ? {
                amount: parseAmountInput(form.amount) ?? '0.00',
                interval_months: form.intervalMonths,
                anchor_month: form.anchorMonth,
                special_months: Object.fromEntries(
                  form.specialMonths.map((month) => [String(month), form.specialFactor]),
                ),
              }
            : form.ruleType === 'rolling_average'
              ? { window_months: form.windowMonths }
              : {}
      return setForecastRule(mandantId, serviceId, {
        mode: form.mode,
        rule_type: form.mode === 'manual' ? form.ruleType : null,
        params,
        adjustment_pct: parseAmountInput(form.adjustmentPct) ?? '0.00',
        shift_months: form.shiftMonths,
      })
    },
    onSuccess: () => {
      setError(null)
      setDraft(null)
      invalidateForecasts()
    },
    onError: (err: unknown) => setError(extractErrorMessage(err, 'Regel konnte nicht gespeichert werden')),
  })

  const resetMutation = useMutation({
    mutationFn: () => resetForecastRule(mandantId, serviceId),
    onSuccess: () => {
      setError(null)
      setDraft(null)
      invalidateForecasts()
    },
    onError: (err: unknown) => setError(extractErrorMessage(err, 'Zurücksetzen fehlgeschlagen')),
  })

  if (ruleQuery.isLoading || !form) {
    return <p className="px-4 py-3 text-sm text-gray-400">Regel wird geladen …</p>
  }
  if (ruleQuery.isError || !ruleQuery.data) {
    return <p className="px-4 py-3 text-sm text-red-500">Regel konnte nicht geladen werden.</p>
  }

  const rule = ruleQuery.data

  return (
    <div className="space-y-4 border-l-2 border-blue-200 bg-gray-50 px-4 py-4 text-sm">
      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Erkanntes Muster
        </h4>
        <p className="text-gray-700">
          {CADENCE_LABELS[rule.detected_cadence] ?? rule.detected_cadence}, {rule.occurrence_count}{' '}
          Buchungen, Median {formatMoney(rule.median_amount)}
        </p>
        <p className="text-xs text-gray-500">{rule.detected_reason}</p>
      </section>

      {rule.backtest && <BacktestSection backtest={rule.backtest} />}

      <section className="space-y-3">
        <div>
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">
            Modus
          </span>
          <div className="inline-flex overflow-hidden rounded border border-gray-300">
            {(Object.keys(MODE_LABELS) as ForecastMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                disabled={!canEdit}
                onClick={() => setForm({ ...form, mode })}
                className={`px-3 py-1.5 text-sm ${
                  form.mode === mode ? 'bg-blue-600 text-white' : 'bg-white hover:bg-gray-50'
                } disabled:opacity-50`}
              >
                {MODE_LABELS[mode]}
              </button>
            ))}
          </div>
        </div>

        {form.mode === 'manual' && (
          <div className="space-y-3 rounded border border-gray-200 bg-white p-3">
            <div>
              <label htmlFor="rule-type" className="mb-1 block text-xs font-medium text-gray-600">
                Regeltyp
              </label>
              <select
                id="rule-type"
                value={form.ruleType}
                disabled={!canEdit}
                onChange={(event) =>
                  setForm({ ...form, ruleType: event.target.value as ForecastRuleType })
                }
                className="rounded border border-gray-300 px-2 py-1.5 text-sm"
              >
                {SELECTABLE_RULES.map((type) => (
                  <option key={type} value={type}>
                    {RULE_LABELS_LONG[type]}
                  </option>
                ))}
              </select>
            </div>

            {form.ruleType === 'fixed_recurring' && (
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label htmlFor="rule-amount" className="mb-1 block text-xs font-medium text-gray-600">
                    Betrag je Zahlung
                  </label>
                  <input
                    id="rule-amount"
                    value={form.amount}
                    disabled={!canEdit}
                    onChange={(event) => setForm({ ...form, amount: event.target.value })}
                    inputMode="decimal"
                    className="w-32 rounded border border-gray-300 px-2 py-1.5 text-right text-sm tabular-nums"
                  />
                </div>
                <div>
                  <label htmlFor="rule-interval" className="mb-1 block text-xs font-medium text-gray-600">
                    Rhythmus
                  </label>
                  <select
                    id="rule-interval"
                    value={form.intervalMonths}
                    disabled={!canEdit}
                    onChange={(event) =>
                      setForm({ ...form, intervalMonths: Number.parseInt(event.target.value, 10) })
                    }
                    className="rounded border border-gray-300 px-2 py-1.5 text-sm"
                  >
                    <option value={1}>monatlich</option>
                    <option value={3}>quartalsweise</option>
                    <option value={6}>halbjährlich</option>
                    <option value={12}>jährlich</option>
                  </select>
                </div>
                {form.intervalMonths > 1 && (
                  <div>
                    <label htmlFor="rule-anchor" className="mb-1 block text-xs font-medium text-gray-600">
                      Zahlungsmonat
                    </label>
                    <select
                      id="rule-anchor"
                      value={form.anchorMonth}
                      disabled={!canEdit}
                      onChange={(event) =>
                        setForm({ ...form, anchorMonth: Number.parseInt(event.target.value, 10) })
                      }
                      className="rounded border border-gray-300 px-2 py-1.5 text-sm"
                    >
                      {MONTHS.map((label, index) => (
                        <option key={label} value={index + 1}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {form.intervalMonths === 1 && (
                  <div>
                    <span className="mb-1 block text-xs font-medium text-gray-600">
                      Sondermonate (z. B. 14. Gehalt)
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {MONTHS.map((label, index) => {
                        const month = index + 1
                        const active = form.specialMonths.includes(month)
                        return (
                          <button
                            key={label}
                            type="button"
                            disabled={!canEdit}
                            aria-pressed={active}
                            onClick={() =>
                              setForm({
                                ...form,
                                specialMonths: active
                                  ? form.specialMonths.filter((entry) => entry !== month)
                                  : [...form.specialMonths, month],
                              })
                            }
                            className={`rounded border px-1.5 py-0.5 text-xs ${
                              active
                                ? 'border-blue-600 bg-blue-50 text-blue-700'
                                : 'border-gray-300 text-gray-500 hover:bg-gray-50'
                            }`}
                          >
                            {label}
                          </button>
                        )
                      })}
                      {form.specialMonths.length > 0 && (
                        <input
                          aria-label="Faktor der Sondermonate"
                          value={form.specialFactor}
                          disabled={!canEdit}
                          onChange={(event) => setForm({ ...form, specialFactor: event.target.value })}
                          className="w-14 rounded border border-gray-300 px-1.5 py-0.5 text-right text-xs"
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {form.ruleType === 'rolling_average' && (
              <div>
                <label htmlFor="rule-window" className="mb-1 block text-xs font-medium text-gray-600">
                  Fenster
                </label>
                <select
                  id="rule-window"
                  value={form.windowMonths}
                  disabled={!canEdit}
                  onChange={(event) =>
                    setForm({ ...form, windowMonths: Number.parseInt(event.target.value, 10) })
                  }
                  className="rounded border border-gray-300 px-2 py-1.5 text-sm"
                >
                  <option value={3}>letzte 3 Monate</option>
                  <option value={6}>letzte 6 Monate</option>
                  <option value={12}>letzte 12 Monate</option>
                </select>
              </div>
            )}

            {form.ruleType === 'manual_plan' && (
              <p className="text-xs text-gray-500">
                Es wird ausschließlich gerechnet, was unten als Planposten steht.
              </p>
            )}
          </div>
        )}

        {form.mode !== 'off' && (
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label htmlFor="rule-adjustment" className="mb-1 block text-xs font-medium text-gray-600">
                Anpassung in %
              </label>
              <input
                id="rule-adjustment"
                value={form.adjustmentPct}
                disabled={!canEdit}
                onChange={(event) => setForm({ ...form, adjustmentPct: event.target.value })}
                inputMode="decimal"
                className="w-24 rounded border border-gray-300 px-2 py-1.5 text-right text-sm tabular-nums"
              />
              <p className="mt-0.5 text-xs text-gray-500">+3 für Indexierung, −30 für Abschlag</p>
            </div>
            <div>
              <label htmlFor="rule-shift" className="mb-1 block text-xs font-medium text-gray-600">
                Zahlungsverzug
              </label>
              <select
                id="rule-shift"
                value={form.shiftMonths}
                disabled={!canEdit}
                onChange={(event) =>
                  setForm({ ...form, shiftMonths: Number.parseInt(event.target.value, 10) })
                }
                className="rounded border border-gray-300 px-2 py-1.5 text-sm"
              >
                {[0, 1, 2, 3].map((months) => (
                  <option key={months} value={months}>
                    {months === 0 ? 'keiner' : `${months} Monat${months > 1 ? 'e' : ''}`}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {canEdit && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saveMutation.isPending ? 'Wird gespeichert …' : 'Regel speichern'}
            </button>
            <button
              type="button"
              onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
            >
              Auf Automatik zurücksetzen
            </button>
            {saveMutation.isSuccess && !saveMutation.isPending && (
              <span className="text-sm text-green-700">Gespeichert.</span>
            )}
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>
        )}
      </section>

      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Vorschau der nächsten zwölf Monate
        </h4>
        <p className="mb-2 text-xs text-gray-500">{rule.effective_reason}</p>
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr className="text-gray-500">
                {rule.preview.map((month) => (
                  <th key={month.period} className="px-2 py-1 text-right font-medium">
                    {formatPeriod(month.period)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {rule.preview.map((month) => (
                  <td
                    key={month.period}
                    className={`px-2 py-1 text-right tabular-nums ${
                      month.is_planned ? 'font-semibold text-blue-700' : 'text-gray-700'
                    }`}
                    title={month.is_planned ? 'Planposten' : undefined}
                  >
                    {formatMoney(month.amount)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <PlannedItemsSection
        mandantId={mandantId}
        serviceId={serviceId}
        canEdit={canEdit}
        items={plannedQuery.data ?? []}
        onChanged={invalidateForecasts}
      />
    </div>
  )
}

function PlannedItemsSection({
  mandantId,
  serviceId,
  canEdit,
  items,
  onChanged,
}: {
  mandantId: string
  serviceId: string
  canEdit: boolean
  items: { id: string; period: string; amount: string; note: string | null }[]
  onChanged: () => void
}) {
  const [period, setPeriod] = useState('')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const defaultPeriod = useMemo(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  }, [])

  const createMutation = useMutation({
    mutationFn: () =>
      createPlannedItem(mandantId, {
        service_id: serviceId,
        period: period || defaultPeriod,
        amount: parseAmountInput(amount) ?? '0.00',
        note: note.trim() || null,
      }),
    onSuccess: () => {
      setAmount('')
      setNote('')
      setError(null)
      onChanged()
    },
    onError: (err: unknown) => setError(extractErrorMessage(err, 'Planposten konnte nicht angelegt werden')),
  })

  const deleteMutation = useMutation({
    mutationFn: (itemId: string) => deletePlannedItem(mandantId, itemId),
    onSuccess: onChanged,
  })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (parseAmountInput(amount) === null || amount.trim() === '') {
      setError('Bitte einen Betrag eingeben, z. B. -1234,56')
      return
    }
    createMutation.mutate()
  }

  return (
    <section>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Planposten
      </h4>
      <p className="mb-2 text-xs text-gray-500">
        Bekannte Beträge, die noch nicht gebucht sind. Sie ersetzen die Schätzung für ihren Monat
        und bleiben von Anpassung und Szenario unberührt. Sobald echte Buchungen eintreffen,
        verrechnet sich der Posten mit ihnen und verliert seine Wirkung — gelöscht wird er nicht.
      </p>

      {items.length > 0 && (
        <ul className="mb-2 divide-y divide-gray-200 rounded border border-gray-200 bg-white">
          {items.map((item) => {
            const state = plannedStatus(item.status)
            return (
            <li
              key={item.id}
              className={`flex items-center justify-between gap-3 px-3 py-1.5 ${
                state.muted ? 'bg-gray-50 text-gray-400' : ''
              }`}
            >
              <span className={state.muted ? '' : 'text-gray-700'}>
                {formatPeriod(item.period)}{' '}
                <span
                  className={`tabular-nums font-medium ${state.muted ? 'line-through' : ''}`}
                >
                  {formatMoney(item.amount)}
                </span>
                {state.badge ? (
                  <span
                    title={state.title}
                    className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 text-[11px] font-medium text-gray-600"
                  >
                    {state.badge}
                  </span>
                ) : null}
                {item.status === 'partly_used' ? (
                  <span className="ml-1.5 text-[11px] tabular-nums text-gray-500">
                    noch {formatMoney(item.remaining_in_month)}
                  </span>
                ) : null}
                {item.note ? <span className="ml-2 text-gray-500">{item.note}</span> : null}
              </span>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(item.id)}
                  className="text-xs text-red-500 hover:underline"
                >
                  Entfernen
                </button>
              )}
            </li>
            )
          })}
        </ul>
      )}

      {canEdit && (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="planned-period" className="mb-1 block text-xs font-medium text-gray-600">
              Monat
            </label>
            <input
              id="planned-period"
              type="month"
              value={period || defaultPeriod}
              onChange={(event) => setPeriod(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label htmlFor="planned-amount" className="mb-1 block text-xs font-medium text-gray-600">
              Betrag
            </label>
            <input
              id="planned-amount"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              inputMode="decimal"
              placeholder="-1234,56"
              className="w-32 rounded border border-gray-300 px-2 py-1.5 text-right text-sm tabular-nums"
            />
          </div>
          <div className="min-w-40 flex-1">
            <label htmlFor="planned-note" className="mb-1 block text-xs font-medium text-gray-600">
              Notiz
            </label>
            <input
              id="planned-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="z. B. Rechnung 2026-114"
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded bg-gray-900 px-3 py-1.5 text-sm text-white hover:bg-gray-700 disabled:opacity-50"
          >
            Hinzufügen
          </button>
          {error && <span className="text-sm text-red-600">{error}</span>}
        </form>
      )}
    </section>
  )
}
