import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { runPartnerAssignmentTest } from '@/api/testing'
import type { AssignmentMismatchItem } from '@/api/testing'
import { useAuthStore } from '@/store/auth-store'

function formatAmount(amount: string, currency: string) {
  return Number(amount).toLocaleString('de-DE', { style: 'currency', currency })
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
    title: 'Test 2: Leistungszuordnung',
    description: 'Prüft Konsistenz zwischen Partner, Leistung und service_assignment_mode.',
    available: false,
    buttonLabel: 'Bald verfügbar',
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

  const mismatchCount = testMutation.data?.mismatches.length ?? 0
  const totalChecked = testMutation.data?.total_checked ?? 0

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
        <button
          type="button"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending || !mandantId || !selectedTest.available}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {testMutation.isPending ? 'Test läuft…' : selectedTest.buttonLabel}
        </button>
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

      {testMutation.isError ? (
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

      {testMutation.data && selectedTest.id === 'partner-assignment' && mismatchCount === 0 ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-700">
          Keine nicht-erklärbaren Zuordnungen gefunden.
        </div>
      ) : null}

      <div className="space-y-3">
        {selectedTest.id === 'partner-assignment' && sortedMismatches.map((item) => (
          <MismatchCard key={item.journal_line.id} item={item} />
        ))}
      </div>
    </div>
  )
}
