import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  runPartnerAssignmentTest,
  runServiceAmountConsistencyTest,
  setServiceAmountConsistencyLineStatus,
} from '@/api/testing'
import type {
  AssignmentMismatchItem,
  AssignmentTestJournalLine,
  ServiceAmountConsistencyItem,
} from '@/api/testing'
import { useAuthStore } from '@/store/auth-store'

function formatAmount(amount: string, currency: string) {
  return Number(amount).toLocaleString('de-DE', { style: 'currency', currency })
}

function getAmountToneClass(amount: string) {
  const numeric = Number(amount)
  if (numeric > 0) {
    return 'text-emerald-700'
  }
  if (numeric < 0) {
    return 'text-rose-700'
  }
  return 'text-slate-900'
}

function formatOutcome(outcome: string) {
  switch (outcome) {
    case 'iban_match':
      return 'IBAN-Match'
    case 'account_match':
      return 'Kontonummer-Match'
    case 'name_match':
      return 'Namens-Match'
    case 'service_matcher_match':
      return 'Leistungs-Matcher-Match'
    case 'service_matcher_ambiguous':
      return 'Leistungs-Matcher mehrdeutig'
    case 'name_ambiguous':
      return 'Name mehrdeutig'
    case 'no_partner_identified':
      return 'Kein Partner identifizierbar'
    case 'new_partner':
      return 'Würde neuen Partner anlegen'
    default:
      return outcome
  }
}

function MismatchCard({ item }: Readonly<{ item: AssignmentMismatchItem }>) {
  const line = item.journal_line

  return (
    <article className="rounded-xl border border-amber-200 bg-amber-50/40 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">{item.reason_code}</p>
          <h3 className="mt-1 text-sm font-semibold text-slate-900">{item.reason_text}</h3>
          <p className="mt-1 text-xs text-slate-600">Regel-Erwartung: {formatOutcome(item.expected_outcome)}</p>
        </div>
        <div className="rounded-lg bg-white px-3 py-2 text-right text-xs text-slate-500">
          <p className="font-mono text-slate-900">{line.booking_date}</p>
          <p className="font-semibold text-slate-900">{formatAmount(line.amount, line.currency)}</p>
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <InfoTile title="Aktueller Partner" value={item.current_partner_name ?? '—'} />
        <InfoTile title="Erwarteter Partner" value={item.expected_partner_name ?? '—'} />
        <InfoTile title="Aktuelle Leistung" value={item.current_service_name ?? '—'} />
        <InfoTile title="Partner (roh)" value={line.partner_name_raw ?? '—'} />
      </div>

      <div className="mt-3 rounded-lg bg-white px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Buchungstext</p>
        <p className="mt-1 text-sm text-slate-700">{line.text ?? '—'}</p>
      </div>

      <details className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-600">Komplette Buchungszeile</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-700">
          {JSON.stringify(line, null, 2)}
        </pre>
      </details>
    </article>
  )
}

function InfoTile({ title, value }: Readonly<{ title: string; value: string }>) {
  return (
    <div className="rounded-lg bg-white px-3 py-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-1 text-sm text-slate-800">{value}</p>
    </div>
  )
}

type ServiceAmountConsistencyCardProps = {
  item: ServiceAmountConsistencyItem
  isUpdatingLineId: string | null
  onToggleLineStatus: (line: AssignmentTestJournalLine) => void
}

function ServiceAmountConsistencyCard({
  item,
  isUpdatingLineId,
  onToggleLineStatus,
}: Readonly<ServiceAmountConsistencyCardProps>) {
  const ignoredLineCount = item.lines.filter((line) =>
    line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok)
  ).length

  return (
    <article className="rounded-xl border border-rose-200 bg-rose-50/40 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-rose-700">Gemischte Vorzeichen</p>
          <h3 className="mt-1 text-sm font-semibold text-slate-900">{item.partner_name ?? '—'} / {item.service_name}</h3>
          <p className="mt-1 text-xs text-slate-600">
            Eingänge: {item.positive_line_count} {' · '} Ausgänge: {item.negative_line_count}
          </p>
          {ignoredLineCount > 0 ? (
            <p className="mt-1 text-xs font-medium text-emerald-700">
              {ignoredLineCount} Buchung{ignoredLineCount === 1 ? '' : 'en'} ist als in Ordnung markiert und wird im Test ignoriert.
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2">
          {item.partner_id ? (
            <Link
              to={`/partners/${item.partner_id}`}
              className="rounded-lg border border-rose-300 bg-white px-3 py-2 text-xs font-semibold text-rose-700 hover:border-rose-400 hover:text-rose-900"
            >
              Partner öffnen
            </Link>
          ) : null}
          <div className="rounded-lg bg-white px-3 py-2 text-right text-xs text-slate-500">
            <p className="font-semibold text-slate-900">{item.lines.length} Buchungen</p>
          </div>
        </div>
      </div>

      <details className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-600">
          Buchungszeilen anzeigen ({item.lines.length})
        </summary>
        <div className="mt-3 space-y-2">
          {item.lines.map((line) => (
            <div
              key={line.id}
              className={[
                'rounded-lg border px-3 py-3',
                line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok)
                  ? 'border-emerald-200 bg-emerald-50/80'
                  : 'border-slate-200 bg-slate-50',
              ].join(' ')}    
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{line.booking_date}</p>
                    {line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok) ? (
                      <span className="rounded-full border border-emerald-300 bg-white px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                        Ist in Ordnung
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-slate-700">{line.text ?? '—'}</p>
                  {line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok) ? (
                    <p className="mt-1 text-xs text-emerald-700">Diese Buchungszeile wird bei Test 2 ignoriert.</p>
                  ) : null}
                </div>
                <div className="text-right">
                  <p className={`text-sm font-semibold ${getAmountToneClass(line.amount)}`}>{formatAmount(line.amount, line.currency)}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Rohdaten: {line.partner_name_raw ?? '—'} / {line.partner_account_raw ?? '—'}
                  </p>
                  <button
                    type="button"
                    onClick={() => onToggleLineStatus(line)}
                    disabled={isUpdatingLineId === line.id}
                    className={[
                      'mt-2 rounded-lg border px-3 py-2 text-xs font-semibold',
                      line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok)
                        ? 'border-emerald-300 bg-white text-emerald-700 hover:border-emerald-400 hover:text-emerald-800'
                        : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:text-slate-900',
                      isUpdatingLineId === line.id ? 'cursor-not-allowed opacity-50' : '',
                    ].join(' ')}
                  >
                    {isUpdatingLineId === line.id
                      ? 'Speichert…'
                      : line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok)
                        ? 'Markierung entfernen'
                        : 'Als in Ordnung markieren'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </details>
    </article>
  )
}

type TestDefinition = {
  id: string
  title: string
  description: string
  available: boolean
  buttonLabel: string
}

const TESTS: TestDefinition[] = [
  {
    id: 'partner-assignment',
    title: 'Test 1: Partnerzuordnung',
    description: 'Validiert Partnerzuordnungen gegen die bestehenden Zuordnungskriterien.',
    available: true,
    buttonLabel: 'Test 1 ausführen',
  },
  {
    id: 'service-link-consistency',
    title: 'Test 2: Service-Betragskonsistenz',
    description: 'Findet Services, die eine Mischung aus Eingängen und Ausgängen haben, und zeigt die Buchungszeilen dazu an.',
    available: true,
    buttonLabel: 'Test 2 ausführen',
  },
  {
    id: 'matcher-quality',
    title: 'Test 3: Matcher-Qualität',
    description: 'Findet problematische oder mehrdeutige Matcher-Konfigurationen.',
    available: false,
    buttonLabel: 'Bald verfügbar',
  },
]

export function TestingPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [selectedTestId, setSelectedTestId] = useState<string>('partner-assignment')

  const selectedTest = useMemo(
    () => TESTS.find((test) => test.id === selectedTestId) ?? TESTS[0],
    [selectedTestId],
  )

  const testMutation = useMutation({
    mutationFn: () => runPartnerAssignmentTest(mandantId),
  })

  const serviceAmountMutation = useMutation({
    mutationFn: () => runServiceAmountConsistencyTest(mandantId),
  })

  const serviceAmountLineStatusMutation = useMutation({
    mutationFn: ({ lineId, splitServiceId, isOk }: { lineId: string; splitServiceId: string; isOk: boolean }) =>
      setServiceAmountConsistencyLineStatus(mandantId, lineId, splitServiceId, isOk),
    onSuccess: () => {
      if (mandantId) {
        serviceAmountMutation.mutate()
      }
    },
  })

  const isPending = selectedTest.id === 'partner-assignment'
    ? testMutation.isPending
    : serviceAmountMutation.isPending
  const hasError = selectedTest.id === 'partner-assignment'
    ? testMutation.isError
    : serviceAmountMutation.isError

  const mismatchCount = testMutation.data?.mismatches.length ?? 0
  const totalChecked = testMutation.data?.total_checked ?? 0
  const inconsistentServiceCount = serviceAmountMutation.data?.inconsistent_services.length ?? 0
  const totalCheckedServices = serviceAmountMutation.data?.total_checked_services ?? 0

  const sortedMismatches = useMemo(() => {
    if (!testMutation.data) return []
    return [...testMutation.data.mismatches].sort(
      (a, b) => b.journal_line.booking_date.localeCompare(a.journal_line.booking_date),
    )
  }, [testMutation.data])

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Testen</h1>
          <p className="mt-1 text-sm text-slate-500">
            Diagnosetests zur Daten- und Zuordnungskonsistenz.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/settings/service-keywords"
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400 hover:text-slate-900"
          >
            Zur Servicekonfiguration
          </Link>
          <button
            type="button"
            onClick={() => {
              if (selectedTest.id === 'partner-assignment') {
                testMutation.mutate()
                return
              }
              if (selectedTest.id === 'service-link-consistency') {
                serviceAmountMutation.mutate()
              }
            }}
            disabled={isPending || !mandantId || !selectedTest.available}
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? 'Test läuft…' : selectedTest.buttonLabel}
          </button>
        </div>
      </div>

      <div className="mb-6 grid gap-3 md:grid-cols-3">
        {TESTS.map((test) => {
          const isSelected = selectedTestId === test.id
          return (
            <button
              key={test.id}
              type="button"
              onClick={() => setSelectedTestId(test.id)}
              className={[
                'rounded-xl border p-4 text-left transition',
                isSelected
                  ? 'border-slate-900 bg-slate-900 text-white shadow-md'
                  : 'border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:shadow-sm',
              ].join(' ')}
            >
              <p className={['text-xs font-semibold uppercase tracking-wide', isSelected ? 'text-slate-200' : 'text-slate-500'].join(' ')}>
                {test.available ? 'Verfügbar' : 'In Arbeit'}
              </p>
              <h2 className="mt-1 text-sm font-semibold">{test.title}</h2>
              <p className={['mt-2 text-xs', isSelected ? 'text-slate-100' : 'text-slate-600'].join(' ')}>
                {test.description}
              </p>
            </button>
          )
        })}
      </div>

      {selectedTest.available ? null : (
        <div className="mb-5 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
          {selectedTest.title} ist noch nicht implementiert. Wähle Test 1, um bereits verfügbare Diagnosen auszuführen.
        </div>
      )}

      {hasError ? (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          Test konnte nicht ausgeführt werden.
        </div>
      ) : null}

      {testMutation.data && selectedTest.id === 'partner-assignment' ? (
        <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm text-slate-600">
            Geprüfte Buchungen: <span className="font-semibold text-slate-900">{totalChecked}</span>
            {' · '}
            Nicht erklärbare Zuordnungen: <span className="font-semibold text-amber-700">{mismatchCount}</span>
          </p>
        </div>
      ) : null}

      {serviceAmountMutation.data && selectedTest.id === 'service-link-consistency' ? (
        <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm text-slate-600">
            Geprüfte Services: <span className="font-semibold text-slate-900">{totalCheckedServices}</span>
            {' · '}
            Services mit gemischten Vorzeichen: <span className="font-semibold text-rose-700">{inconsistentServiceCount}</span>
          </p>
        </div>
      ) : null}

      {testMutation.data && selectedTest.id === 'partner-assignment' && mismatchCount === 0 ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-700">
          Keine nicht-erklärbaren Zuordnungen gefunden.
        </div>
      ) : null}

      {serviceAmountMutation.data && selectedTest.id === 'service-link-consistency' && inconsistentServiceCount === 0 ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-700">
          Keine Services mit gemischten Eingangs- und Ausgangsbuchungen gefunden.
        </div>
      ) : null}

      <div className="space-y-3">
        {selectedTest.id === 'partner-assignment' && sortedMismatches.map((item) => (
          <MismatchCard key={item.journal_line.id} item={item} />
        ))}
        {selectedTest.id === 'service-link-consistency' && serviceAmountMutation.data?.inconsistent_services.map((item) => (
          <ServiceAmountConsistencyCard
            key={item.service_id}
            item={item}
            isUpdatingLineId={serviceAmountLineStatusMutation.isPending ? serviceAmountLineStatusMutation.variables?.lineId ?? null : null}
            onToggleLineStatus={(line) => {
              const currentOk = line.splits.some((sp) => sp.service_id === item.service_id && sp.amount_consistency_ok)
              serviceAmountLineStatusMutation.mutate({
                lineId: line.id,
                splitServiceId: item.service_id,
                isOk: !currentOk,
              })
            }}
          />
        ))}
      </div>
    </div>
  )
}
