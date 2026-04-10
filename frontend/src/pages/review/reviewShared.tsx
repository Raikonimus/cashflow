import { NavLink } from 'react-router-dom'

export const reviewTypeLabels: Record<string, string> = {
  name_match: 'Partner-Prüfung',
  name_match_with_iban: 'Partner-Prüfung',
  partner_name_match: 'Partner-Prüfung',
  service_assignment: 'Leistungs-Zuordnung',
  service_type_review: 'Leistungstyp',
}

export const serviceTypeLabels: Record<string, string> = {
  customer: 'Kunde',
  supplier: 'Lieferant',
  employee: 'Mitarbeiter',
  authority: 'Behörde',
  unknown: 'Unbekannt',
}

export const reviewStatusLabels: Record<string, string> = {
  open: 'Offen',
  confirmed: 'Bestätigt',
  adjusted: 'Korrigiert',
  rejected: 'Abgelehnt',
}

export function formatCurrency(amount: string, currency = 'EUR') {
  const value = Number(amount)
  if (Number.isNaN(value)) return amount
  return value.toLocaleString('de-DE', { style: 'currency', currency })
}

export function formatReviewReason(reason: string | undefined) {
  if (!reason) return 'Automatische Prüfung'
  if (reason === 'multiple_matches') return 'Mehrere Matcher passen auf diese Buchung.'
  if (reason === 'single_match') return 'Ein Matcher passt eindeutig auf diese Buchung.'
  if (reason === 'no_match_base_service') return 'Keine passende Leistung gefunden, Basisleistung gewählt.'
  if (reason.startsWith('keyword:')) return `Keyword-Regel: ${reason.replace('keyword:', '')}`
  if (reason === 'amount<=0') return 'Automatisch aus negativem Betrag abgeleitet.'
  if (reason === 'amount>0') return 'Automatisch aus positivem Betrag abgeleitet.'
  return reason.replaceAll('_', ' ')
}

export function ReviewSubnav({
  queueCount,
  typeCount,
}: {
  queueCount?: number
  typeCount?: number
}) {
  const linkBase = 'inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors'
  return (
    <div className="mb-8 flex flex-wrap gap-3">
      <NavLink
        to="/review"
        end
        className={({ isActive }) => `${linkBase} ${isActive ? 'bg-amber-500 text-white' : 'bg-white text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-amber-50'}`}
      >
        Queue
        {queueCount !== undefined && queueCount > 0 ? <Badge count={queueCount} inverted /> : null}
      </NavLink>
      <NavLink
        to="/review/service-types"
        className={({ isActive }) => `${linkBase} ${isActive ? 'bg-teal-600 text-white' : 'bg-white text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-teal-50'}`}
      >
        Leistungstypen
        {typeCount !== undefined && typeCount > 0 ? <Badge count={typeCount} inverted /> : null}
      </NavLink>
      <NavLink
        to="/review/archive"
        className={({ isActive }) => `${linkBase} ${isActive ? 'bg-slate-800 text-white' : 'bg-white text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-slate-100'}`}
      >
        Archiv
      </NavLink>
    </div>
  )
}

export function InlineNotice({
  tone,
  message,
}: {
  tone: 'success' | 'error'
  message: string
}) {
  return (
    <div className={`mb-5 rounded-2xl border px-4 py-3 text-sm ${tone === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-rose-200 bg-rose-50 text-rose-700'}`}>
      {message}
    </div>
  )
}

export function EmptyReviewState({
  title,
  text,
}: {
  title: string
  text: string
}) {
  return (
    <div className="rounded-[2rem] border border-dashed border-slate-300 bg-[linear-gradient(135deg,#fff7ed,white_45%,#ecfeff)] px-8 py-16 text-center shadow-sm">
      <div className="mx-auto mb-5 h-16 w-16 rounded-2xl bg-[radial-gradient(circle_at_top_left,#f59e0b,transparent_58%),linear-gradient(135deg,#0f172a,#334155)]" />
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">{text}</p>
    </div>
  )
}

function Badge({ count, inverted = false }: { count: number; inverted?: boolean }) {
  return (
    <span className={`inline-flex min-w-6 items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-semibold ${inverted ? 'bg-white/20 text-current' : 'bg-amber-500 text-white'}`}>
      {count}
    </span>
  )
}