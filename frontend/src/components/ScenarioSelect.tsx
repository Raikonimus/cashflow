import type { Scenario } from '@/api/forecast'

const OPTIONS: { value: Scenario; label: string; title: string }[] = [
  {
    value: 'low',
    label: 'Pessimistisch',
    title: 'Stresstest: jede Regel irrt gleichzeitig zuungunsten des Saldos',
  },
  { value: 'expected', label: 'Erwartet', title: 'Erwartungswert der Regeln' },
  {
    value: 'high',
    label: 'Optimistisch',
    title: 'Gegenprobe: jede Regel irrt gleichzeitig zugunsten des Saldos',
  },
]

const STRESS_HINT =
  'Stresstest, keine Wahrscheinlichkeit: Die Bandbreite unterstellt, dass alle Regeln ' +
  'gleichzeitig in dieselbe Richtung danebenliegen — je Regel 10 % bei hoher, 25 % bei ' +
  'mittlerer und 50 % bei niedriger Confidence. In der Realität gleichen sich Fehler ' +
  'über viele Leistungen teilweise aus.'

/**
 * Die Bandbreite richtet sich nach der Confidence der jeweiligen Regel: eine sicher
 * erkannte Leistung schwankt um 10 %, eine unsichere um 50 %.
 */
export function ScenarioSelect({
  value,
  onChange,
}: {
  value: Scenario
  onChange: (scenario: Scenario) => void
}) {
  return (
    <div className="inline-flex flex-col gap-1">
      <div
        className="inline-flex overflow-hidden rounded border border-gray-300"
        role="group"
        aria-label="Szenario"
      >
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            title={option.title}
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
            className={`px-3 py-1.5 text-sm ${
              value === option.value ? 'bg-gray-900 text-white' : 'bg-white hover:bg-gray-50'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {value !== 'expected' && <p className="max-w-md text-xs text-amber-700">{STRESS_HINT}</p>}
    </div>
  )
}
