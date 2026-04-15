import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { listReviewArchive } from '@/api/review'
import { EmptyReviewState, formatCurrency, formatReviewReason, reviewStatusLabels, reviewTypeLabels, serviceTypeLabels } from './reviewShared'

export function ReviewArchivePage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [itemType, setItemType] = useState('')
  const [resolvedByUserId, setResolvedByUserId] = useState('')
  const [resolvedFrom, setResolvedFrom] = useState('')
  const [resolvedTo, setResolvedTo] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['review-archive', mandantId, itemType, resolvedByUserId, resolvedFrom, resolvedTo],
    queryFn: () => listReviewArchive(mandantId, {
      itemType: itemType || undefined,
      resolvedByUserId: resolvedByUserId || undefined,
      resolvedFrom: resolvedFrom || undefined,
      resolvedTo: resolvedTo || undefined,
      size: 100,
    }),
    enabled: !!mandantId,
  })

  const items = data?.items ?? []

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Review</p>
        <div className="mt-2 flex items-start justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Archiv</h1>
          <Link to="/review" className="shrink-0 rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">← Offene Entscheidungen</Link>
        </div>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
          Bereits bestätigte, korrigierte oder abgelehnte Prüfentscheidungen mit Filtern für Typ, Bearbeiter und Zeitraum.
        </p>
      </div>

      <section className="mb-6 grid gap-3 rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-4">
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Typ
          <select value={itemType} onChange={(event) => setItemType(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900">
            <option value="">Alle</option>
            <option value="service_assignment">Leistungs-Zuordnung</option>
            <option value="service_type_review">Leistungstyp</option>
            <option value="name_match_with_iban">Partner-Prüfung</option>
            <option value="no_partner_identified">Kein Partner erkannt</option>
            <option value="service_matcher_ambiguous">Mehrdeutige Leistung</option>
          </select>
        </label>
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Bearbeiter-ID
          <input value={resolvedByUserId} onChange={(event) => setResolvedByUserId(event.target.value)} placeholder="UUID" className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900" />
        </label>
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Von
          <input type="date" value={resolvedFrom} onChange={(event) => setResolvedFrom(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900" />
        </label>
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Bis
          <input type="date" value={resolvedTo} onChange={(event) => setResolvedTo(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900" />
        </label>
      </section>

      {isLoading ? (
        <div className="flex min-h-[14rem] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-300 border-t-slate-800" /></div>
      ) : items.length === 0 ? (
        <EmptyReviewState title="Kein Archivtreffer" text="Für die gewählten Filter wurden noch keine abgeschlossenen Review-Entscheidungen gefunden." />
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <article key={item.id} className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">{reviewTypeLabels[item.item_type] ?? item.item_type}</span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{reviewStatusLabels[item.status] ?? item.status}</span>
                  </div>
                  <p className="mt-3 text-sm text-slate-500">{formatReviewReason(item.context.reason)}</p>
                </div>
                <div className="text-right text-xs text-slate-400">
                  <div>Erledigt: {item.resolved_at ? new Date(item.resolved_at).toLocaleString('de-DE') : '—'}</div>
                  <div className="mt-1">Bearbeiter: {item.resolved_by ?? '—'}</div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {item.journal_line ? (
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Buchung</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{item.journal_line.partner_name_raw ?? 'Ohne Partnername'}</p>
                    <p className="mt-1 text-sm text-slate-500">{item.journal_line.text ?? 'Kein Buchungstext vorhanden'}</p>
                    <p className="mt-2 text-sm text-slate-700">{formatCurrency(item.journal_line.amount, item.journal_line.currency)}</p>
                  </div>
                ) : null}
                {item.service ? (
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Leistung</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{item.service.name}</p>
                    <p className="mt-1 text-sm text-slate-500">Typ: {serviceTypeLabels[item.service.service_type]}</p>
                    <p className="mt-1 text-sm text-slate-500">Steuersatz: {item.service.tax_rate}%</p>
                  </div>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}