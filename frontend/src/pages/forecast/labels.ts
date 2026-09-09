import type { ForecastMode, ForecastRuleType } from '@/api/forecast'

export const MONTHS = [
  'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez',
]

export const MODE_LABELS: Record<ForecastMode, string> = {
  auto: 'Automatisch',
  manual: 'Händisch',
  off: 'Keine Prognose',
}

/** Ausführliche Bezeichnungen für den Editor. */
export const RULE_LABELS_LONG: Record<ForecastRuleType, string> = {
  fixed_recurring: 'Fester Betrag im Rhythmus',
  rolling_average: 'Gleitender Durchschnitt',
  same_period_last_year: 'Vorjahresmonat',
  seasonal_profile: 'Saisonprofil',
  manual_plan: 'Nur Planposten',
  none: 'Keine Prognose',
}

/** Kurzform für die Tabellenspalte. */
export const RULE_LABELS_SHORT: Record<ForecastRuleType, string> = {
  fixed_recurring: 'Fester Betrag',
  rolling_average: 'Gleitender Ø',
  same_period_last_year: 'Vorjahresmonat',
  seasonal_profile: 'Saisonprofil',
  manual_plan: 'Nur Planposten',
  none: 'Keine Prognose',
}

export const SELECTABLE_RULES: ForecastRuleType[] = [
  'fixed_recurring',
  'rolling_average',
  'same_period_last_year',
  'seasonal_profile',
  'manual_plan',
]

export const CADENCE_LABELS: Record<string, string> = {
  monthly: 'monatlich',
  quarterly: 'mehrmonatig',
  annual: 'jährlich',
  irregular: 'unregelmäßig',
  none: 'kein Muster',
}

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'hoch',
  medium: 'mittel',
  low: 'niedrig',
}

export function formatPeriod(period: string): string {
  const [year, month] = period.split('-')
  const index = Number.parseInt(month ?? '', 10) - 1
  if (!year || index < 0 || index > 11) return period
  return `${MONTHS[index]} ${year.slice(2)}`
}

/** Relativen Fehler als Prozentangabe — die Zahl, die die Prognose bewertet. */
export function formatAccuracy(relativeError: string | null): string | null {
  if (relativeError === null) return null
  const value = Number.parseFloat(relativeError)
  if (Number.isNaN(value)) return null
  return `±${Math.round(value * 100)} %`
}

/** Ampelfarbe zur gemessenen Treffsicherheit — dieselben Schwellen wie im Backend. */
export function accuracyClass(relativeError: string | null): string {
  const value = relativeError === null ? Number.NaN : Number.parseFloat(relativeError)
  if (Number.isNaN(value)) return 'bg-gray-200 text-gray-700'
  if (value <= 0.1) return 'bg-green-100 text-green-800'
  if (value <= 0.3) return 'bg-amber-100 text-amber-800'
  return 'bg-red-100 text-red-800'
}

export const CANDIDATE_HINT =
  'Jede Regel wurde nur auf den Daten vor dem Prüfzeitraum gebildet und dann daran gemessen. ' +
  'Kleinster Score gewinnt. Die Nullprognose läuft als Vergleichslinie mit, wird aber nie gewählt.'

/** Einheitliche Kennzeichnung fuer alles, was von Hand eingestellt wurde. Eigene Farbe,
 *  damit sie sich beim Ueberfliegen nicht mit der Guete-Ampel (gruen/gelb/rot) mischt. */
export const HAND_SET_CLASS = 'bg-indigo-100 text-indigo-800'

/** Prozentanpassung als Kurzform: "+100 %", "-10 %". Null ergibt null. */
export function formatAdjustment(adjustmentPct: string): string | null {
  const value = Number.parseFloat(adjustmentPct)
  if (Number.isNaN(value) || value === 0) return null
  const rounded = Number.isInteger(value) ? value : Math.round(value * 100) / 100
  return `${value > 0 ? '+' : '\u2212'}${Math.abs(rounded).toLocaleString('de-DE')} %`
}
