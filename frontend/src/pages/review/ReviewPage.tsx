import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { adjustReviewItem, confirmReviewItem, listReviewItems, newPartnerReviewItem, rejectReviewItem, reassignReviewItem } from '@/api/review'
import type { ReviewItem } from '@/api/review'
import { listPartners } from '@/api/partners'
import type { PartnerListItem } from '@/api/partners'
import { listPartnerServices } from '@/api/services'
import type { ServiceListItem } from '@/api/services'
import { EmptyReviewState, formatCurrency, formatReviewReason, InlineNotice, ReviewSubnav, reviewTypeLabels, serviceTypeLabels } from './reviewShared'

const outcomeLabels: Record<string, string> = {
  iban_match: 'IBAN-Treffer',
  name_match: 'Namens-Treffer',
  new_partner: 'Neuer Partner',
}

export function ReviewPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['review', mandantId, 'open'],
    queryFn: () => listReviewItems(mandantId, { status: 'open', size: 100 }),
    enabled: !!mandantId,
  })

  const items = data?.items ?? []
  const typeReviews = items.filter((item) => item.item_type === 'service_type_review')

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-400 border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Review</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Offene Entscheidungen</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
          Partner-Zuordnungen, Leistungsvorschläge und automatisch gesetzte Leistungstypen an einer Stelle prüfen und sauber auflösen.
        </p>
      </div>

      <ReviewSubnav queueCount={items.length} typeCount={typeReviews.length} />
      {notice ? <InlineNotice tone={notice.tone} message={notice.message} /> : null}

      {items.length === 0 ? (
        <EmptyReviewState title="Queue ist leer" text="Es gibt aktuell keine offenen Prüfungen. Neue automatische Entscheidungen landen hier sofort wieder sichtbar im Team-Workflow." />
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              mandantId={mandantId}
              onResolved={async (message) => {
                await queryClient.invalidateQueries({ queryKey: ['review'] })
                setNotice({ tone: 'success', message })
              }}
              onError={(message) => setNotice({ tone: 'error', message })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ReviewCard({
  item,
  mandantId,
  onResolved,
  onError,
}: {
  item: ReviewItem
  mandantId: string
  onResolved: (message: string) => void | Promise<void>
  onError: (message: string) => void
}) {
  const [mode, setMode] = useState<'idle' | 'reassign' | 'new-partner' | 'service-select'>('idle')
  const [partnerQuery, setPartnerQuery] = useState('')
  const [partnerResults, setPartnerResults] = useState<PartnerListItem[]>([])
  const [newPartnerName, setNewPartnerName] = useState('')

  const confirmMutation = useMutation({
    mutationFn: () => confirmReviewItem(mandantId, item.id),
    onSuccess: async () => onResolved(item.item_type === 'service_assignment' ? 'Leistungsvorschlag wurde übernommen.' : 'Review-Item wurde bestätigt.'),
    onError: () => onError('Aktion konnte nicht gespeichert werden.'),
  })

  const rejectMutation = useMutation({
    mutationFn: () => rejectReviewItem(mandantId, item.id),
    onSuccess: async () => onResolved('Review-Item wurde abgelehnt.'),
    onError: () => onError('Ablehnung konnte nicht gespeichert werden.'),
  })

  const reassignMutation = useMutation({
    mutationFn: (partnerId: string) => reassignReviewItem(mandantId, item.id, partnerId),
    onSuccess: async () => onResolved('Partner wurde korrigiert.'),
    onError: () => onError('Partner konnte nicht gesetzt werden.'),
  })

  const newPartnerMutation = useMutation({
    mutationFn: () => newPartnerReviewItem(mandantId, item.id, newPartnerName.trim()),
    onSuccess: async () => onResolved('Neuer Partner wurde angelegt und zugewiesen.'),
    onError: () => onError('Neuer Partner konnte nicht angelegt werden.'),
  })

  const adjustServiceMutation = useMutation({
    mutationFn: (serviceId: string) => adjustReviewItem(mandantId, item.id, { service_id: serviceId }),
    onSuccess: async () => onResolved('Leistungs-Zuordnung wurde korrigiert.'),
    onError: () => onError('Leistung konnte nicht gesetzt werden.'),
  })

  const { data: services = [] } = useQuery({
    queryKey: ['partner-services', mandantId, item.journal_line?.partner_id],
    queryFn: () => listPartnerServices(mandantId, item.journal_line!.partner_id!),
    enabled: mode === 'service-select' && !!item.journal_line?.partner_id,
  })

  async function searchPartners(q: string) {
    setPartnerQuery(q)
    if (q.trim().length < 2) {
      setPartnerResults([])
      return
    }
    const data = await listPartners(mandantId, 1, 8, false, q)
    setPartnerResults(data.items.filter((partner) => partner.is_active))
  }

  return (
    <article className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">{reviewTypeLabels[item.item_type] ?? item.item_type}</span>
            {item.item_type === 'service_type_review' ? (
              <span className="rounded-full bg-teal-100 px-3 py-1 text-xs font-semibold text-teal-700">Spezialansicht</span>
            ) : null}
          </div>
          <h2 className="mt-3 text-lg font-semibold text-slate-900">{resolveHeadline(item)}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">{formatReviewReason(item.context.reason ?? item.context.match_outcome)}</p>
        </div>
        {item.journal_line ? (
          <div className="rounded-2xl bg-slate-50 px-4 py-3 text-right text-sm text-slate-600">
            <p className="font-semibold text-slate-900">{formatCurrency(item.journal_line.amount, item.journal_line.currency)}</p>
            <p className="mt-1">{item.journal_line.booking_date}</p>
          </div>
        ) : null}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <InfoTile title="Buchung" body={item.journal_line?.text ?? item.context.text ?? 'Kein Buchungstext vorhanden'} footer={item.journal_line?.partner_name_raw ?? item.context.partner_name_raw ?? 'Ohne Partnername'} />
        <InfoTile title="Aktuell" body={resolveCurrentState(item)} footer={item.journal_line?.service_assignment_mode ? `Modus: ${item.journal_line.service_assignment_mode}` : undefined} />
        <InfoTile title="Vorschlag" body={resolveSuggestedState(item)} footer={item.item_type === 'service_type_review' ? `Zeilen: ${item.assigned_journal_lines.length}` : undefined} />
      </div>

      {item.item_type === 'service_type_review' ? (
        <div className="mt-5 flex flex-wrap gap-2">
          <Link to="/review/service-types" className="rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700">Typ-Review öffnen</Link>
          <Link to="/review/archive" className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Zum Archiv</Link>
        </div>
      ) : (
        <>
          {mode === 'idle' ? (
            <div className="mt-5 flex flex-wrap gap-2">
              <button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
                {item.item_type === 'service_assignment' ? 'Vorschlag übernehmen' : 'Bestätigen'}
              </button>
              {item.item_type === 'service_assignment' ? (
                <>
                  <button onClick={() => setMode('service-select')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Andere Leistung</button>
                  <button onClick={() => rejectMutation.mutate()} disabled={rejectMutation.isPending} className="rounded-xl border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50">Ablehnen</button>
                </>
              ) : (
                <>
                  <button onClick={() => setMode('reassign')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Anderer Partner</button>
                  <button onClick={() => setMode('new-partner')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Neuer Partner</button>
                </>
              )}
            </div>
          ) : null}

          {mode === 'reassign' ? (
            <div className="mt-4 rounded-2xl bg-slate-50 p-4">
              <input value={partnerQuery} onChange={(event) => searchPartners(event.target.value)} placeholder="Partner suchen…" className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" />
              <div className="mt-3 space-y-2">
                {partnerResults.map((partner) => (
                  <button key={partner.id} onClick={() => reassignMutation.mutate(partner.id)} className="block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100">{partner.name}</button>
                ))}
              </div>
              <button onClick={() => setMode('idle')} className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Abbrechen</button>
            </div>
          ) : null}

          {mode === 'new-partner' ? (
            <div className="mt-4 flex flex-wrap gap-3 rounded-2xl bg-slate-50 p-4">
              <input value={newPartnerName} onChange={(event) => setNewPartnerName(event.target.value)} placeholder="Neuer Partnername" className="min-w-[16rem] flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm" />
              <button onClick={() => newPartnerMutation.mutate()} disabled={!newPartnerName.trim() || newPartnerMutation.isPending} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50">Anlegen & zuweisen</button>
              <button onClick={() => setMode('idle')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-white">Abbrechen</button>
            </div>
          ) : null}

          {mode === 'service-select' ? (
            <div className="mt-4 rounded-2xl bg-slate-50 p-4">
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {(services as ServiceListItem[]).map((service) => (
                  <button key={service.id} onClick={() => adjustServiceMutation.mutate(service.id)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left hover:bg-slate-100">
                    <p className="text-sm font-semibold text-slate-900">{service.name}</p>
                    <p className="mt-1 text-xs text-slate-500">{serviceTypeLabels[service.service_type]} · {service.tax_rate}%</p>
                  </button>
                ))}
              </div>
              <button onClick={() => setMode('idle')} className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Abbrechen</button>
            </div>
          ) : null}
        </>
      )}
    </article>
  )
}

function resolveHeadline(item: ReviewItem) {
  if (item.item_type === 'service_assignment') {
    return item.journal_line?.partner_name_raw ?? 'Leistungs-Zuordnung prüfen'
  }
  if (item.item_type === 'service_type_review') {
    return item.service?.name ?? 'Leistungstyp prüfen'
  }
  return item.context.partner_name_raw ?? item.journal_line?.partner_name_raw ?? 'Partner-Zuordnung prüfen'
}

function resolveCurrentState(item: ReviewItem) {
  if (item.item_type === 'service_assignment') {
    return item.context.current_service_id ? `Service-ID ${item.context.current_service_id}` : 'Keine Leistung hinterlegt'
  }
  if (item.item_type === 'service_type_review') {
    return serviceTypeLabels[item.context.previous_type ?? item.service?.service_type ?? 'unknown']
  }
  return outcomeLabels[item.context.match_outcome ?? ''] ?? 'Automatische Zuordnung'
}

function resolveSuggestedState(item: ReviewItem) {
  if (item.item_type === 'service_assignment') {
    return item.context.proposed_service_id ? `Service-ID ${item.context.proposed_service_id}` : `${item.context.matching_services?.length ?? 0} mögliche Leistungen`
  }
  if (item.item_type === 'service_type_review') {
    return serviceTypeLabels[item.context.auto_assigned_type ?? 'unknown']
  }
  return item.context.suggested_partner_name ?? 'Partner manuell prüfen'
}

function InfoTile({ title, body, footer }: { title: string; body: string; footer?: string }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 text-sm font-semibold text-slate-900">{body}</p>
      {footer ? <p className="mt-1 text-sm text-slate-500">{footer}</p> : null}
    </div>
  )
}
