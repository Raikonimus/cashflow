import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuthStore } from '@/store/auth-store'
import { adjustReviewItem, confirmReviewItem, listReviewItems, newPartnerReviewItem, rejectReviewItem, reassignReviewItem } from '@/api/review'
import type { NoPartnerDiagnosis, ReviewItem } from '@/api/review'
import { listPartners } from '@/api/partners'
import type { PartnerListItem } from '@/api/partners'
import { listPartnerServices } from '@/api/services'
import type { ServiceListItem } from '@/api/services'
import { EmptyReviewState, formatCurrency, formatReviewReason, InlineNotice, reviewTypeLabels, serviceTypeLabels } from './reviewShared'

const outcomeLabels: Record<string, string> = {
  iban_match: 'IBAN-Treffer',
  name_match: 'Namens-Treffer',
  new_partner: 'Neuer Partner',
}

type ReviewTab = 'all' | 'no_partner' | 'new_partner' | 'iban' | 'service' | 'service_type' | 'manual_service'

const TAB_CONFIG: { id: ReviewTab; label: string; types: string[] | null }[] = [
  { id: 'all', label: 'Alle', types: null },
  { id: 'no_partner', label: 'Kein Partner', types: ['no_partner_identified'] },
  { id: 'new_partner', label: 'Neuer Partner', types: ['new_partner'] },
  { id: 'iban', label: 'IBAN-Abweichung', types: ['name_match_with_iban'] },
  { id: 'service', label: 'Leistung unklar', types: ['service_assignment', 'service_matcher_ambiguous'] },
  { id: 'service_type', label: 'Leistungstyp', types: ['service_type_review'] },
  { id: 'manual_service', label: 'Manuelle Leistung', types: ['manual_service_assignment'] },
]

export function ReviewPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)
  const [activeTab, setActiveTab] = useState<ReviewTab>('all')

  const { data, isLoading } = useQuery({
    queryKey: ['review', mandantId, 'open'],
    queryFn: () => listReviewItems(mandantId, { status: 'open', size: 100 }),
    enabled: !!mandantId,
  })

  const items = data?.items ?? []

  function countForTab(tab: ReviewTab): number {
    if (tab === 'all') return items.length
    const types = TAB_CONFIG.find((t) => t.id === tab)?.types ?? []
    return items.filter((item) => types.includes(item.item_type)).length
  }

  const tabConfig = TAB_CONFIG.find((t) => t.id === activeTab)
  const visibleItems =
    activeTab === 'all'
      ? items
      : items.filter((item) => (tabConfig?.types ?? []).includes(item.item_type))

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
        <div className="mt-2 flex items-start justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Offene Entscheidungen</h1>
          <Link to="/review/archive" className="shrink-0 rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">Archiv</Link>
        </div>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
          Partner-Zuordnungen, Leistungsvorschläge und automatisch gesetzte Leistungstypen an einer Stelle prüfen und sauber auflösen.
        </p>
      </div>

      {notice ? <InlineNotice tone={notice.tone} message={notice.message} /> : null}

      <div className="mb-6 flex flex-wrap gap-2">
        {TAB_CONFIG.map((tab) => {
          const count = countForTab(tab.id)
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'bg-white text-slate-600 shadow-sm ring-1 ring-slate-200 hover:bg-amber-50'
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span
                  className={`inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-semibold ${
                    isActive ? 'bg-white/20 text-white' : 'bg-amber-100 text-amber-700'
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {visibleItems.length === 0 ? (
        <EmptyReviewState
          title={activeTab === 'all' ? 'Queue ist leer' : `Keine Einträge in "${tabConfig?.label}"`}
          text={
            activeTab === 'all'
              ? 'Es gibt aktuell keine offenen Prüfungen. Neue automatische Entscheidungen landen hier sofort wieder sichtbar im Team-Workflow.'
              : 'Für diesen Typ gibt es aktuell keine offenen Prüfungen.'
          }
        />
      ) : (
        <div className="space-y-4">
          {visibleItems.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              mandantId={mandantId}
              onResolved={async (message) => {
                await Promise.all([
                  queryClient.invalidateQueries({ queryKey: ['review'] }),
                  queryClient.invalidateQueries({ queryKey: ['review-badge'] }),
                ])
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
  const [mode, setMode] = useState<'idle' | 'reassign' | 'new-partner' | 'service-select' | 'type-adjust'>('idle')
  const [partnerQuery, setPartnerQuery] = useState('')
  const [partnerResults, setPartnerResults] = useState<PartnerListItem[]>([])
  const [newPartnerName, setNewPartnerName] = useState('')
  const [serviceTypeDraft, setServiceTypeDraft] = useState(
    item.context.auto_assigned_type ?? item.service?.service_type ?? 'unknown'
  )
  const [taxRateDraft, setTaxRateDraft] = useState(item.service?.tax_rate ?? '')
  const [erfolgsneutralDraft, setErfolgsneutralDraft] = useState(Boolean(item.service?.erfolgsneutral))

  const confirmMutation = useMutation({
    mutationFn: () => confirmReviewItem(mandantId, item.id),
    onSuccess: async () => onResolved(
      item.item_type === 'service_assignment' ? 'Leistungsvorschlag wurde übernommen.' :
      item.item_type === 'service_type_review' ? 'Leistungstyp wurde freigegeben.' :
      'Review-Item wurde bestätigt.'
    ),
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

  const adjustTypeMutation = useMutation({
    mutationFn: () => adjustReviewItem(mandantId, item.id, {
      service_type: serviceTypeDraft,
      tax_rate: taxRateDraft || undefined,
      erfolgsneutral: erfolgsneutralDraft,
    }),
    onSuccess: async () => onResolved('Leistungstyp wurde korrigiert.'),
    onError: () => onError('Korrektur konnte nicht gespeichert werden.'),
  })

  const { data: services = [] } = useQuery({
    queryKey: ['partner-services', mandantId, item.journal_line?.partner_id],
    queryFn: () => listPartnerServices(mandantId, item.journal_line!.partner_id!),
    enabled: (mode === 'service-select' || item.item_type === 'manual_service_assignment') && !!item.journal_line?.partner_id,
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

  const isServiceTypeReview = item.item_type === 'service_type_review'
  const isManualServiceAssignment = item.item_type === 'manual_service_assignment'
  const lineCount = item.assigned_journal_lines.length

  return (
    <article className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">{reviewTypeLabels[item.item_type] ?? item.item_type}</span>
            {isServiceTypeReview && (
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                {lineCount} Buchungszeile{lineCount !== 1 ? 'n' : ''}
              </span>
            )}
          </div>
          <h2 className="mt-3 text-lg font-semibold text-slate-900">{resolveHeadline(item)}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            {isManualServiceAssignment
              ? (item.journal_line?.text ?? '—')
              : formatReviewReason(item.context.reason ?? item.context.match_outcome)}
          </p>
        </div>
        {item.journal_line ? (
          <div className="rounded-2xl bg-slate-50 px-4 py-3 text-right text-sm text-slate-600">
            <p className="font-semibold text-slate-900">{formatCurrency(item.journal_line.amount, item.journal_line.currency)}</p>
            <p className="mt-1">{item.journal_line.booking_date}</p>
          </div>
        ) : null}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {isServiceTypeReview ? (
          <InfoTile title="Partner" body={item.service?.partner_name ?? 'Unbekannter Partner'} />
        ) : isManualServiceAssignment ? (
          <InfoTile
            title="Partner"
            body={item.journal_line?.partner_name ?? item.journal_line?.partner_name_raw ?? 'Unbekannt'}
            footer={item.journal_line?.partner_id
              ? <Link to={`/partners/${item.journal_line.partner_id}`} className="text-blue-600 hover:underline text-xs">Zur Partnerseite →</Link>
              : undefined
            }
          />
        ) : (
          <InfoTile title="Buchung" body={item.journal_line?.text ?? item.context.text ?? 'Kein Buchungstext vorhanden'} footer={item.journal_line?.partner_name_raw ?? item.context.partner_name_raw ?? 'Ohne Partnername'} />
        )}
        <InfoTile title="Aktuell" body={resolveCurrentState(item)} footer={item.journal_line?.splits?.[0]?.assignment_mode ? `Modus: ${item.journal_line.splits[0].assignment_mode}` : undefined} />
        <InfoTile
          title="Vorschlag"
          body={resolveSuggestedState(item)}
          footer={isServiceTypeReview ? `Kriterium: ${resolveCriterionLabel(item.context.reason)}` : undefined}
        />
      </div>

      {item.item_type === 'no_partner_identified' ? (
        item.context.diagnosis
          ? <NoPartnerDiagnosisPanel diagnosis={item.context.diagnosis} />
          : <NoPartnerRawDataPanel context={item.context} />
      ) : null}

      {item.item_type === 'name_match_with_iban' ? (
        <IbanDeviationPanel item={item} />
      ) : null}

      {isServiceTypeReview && lineCount > 0 ? (
        <div className="mt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Betroffene Buchungszeilen ({lineCount})
          </p>
          <div className="space-y-1">
            {item.assigned_journal_lines.map((line) => (
              <div key={line.id} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-1.5 text-xs text-slate-700">
                <span className="w-20 shrink-0 text-slate-400">{line.booking_date}</span>
                <span className="shrink-0 w-20 text-right font-mono font-semibold text-slate-900">{formatCurrency(line.amount, line.currency)}</span>
                <span className="w-32 shrink-0 truncate text-slate-600 font-medium">{line.partner_name ?? line.partner_name_raw ?? '—'}</span>
                <span className="truncate text-slate-500">{line.text ?? '—'}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {mode === 'idle' ? (
        <div className="mt-5 flex flex-wrap gap-2">
          {isManualServiceAssignment ? (
            <div className="w-full">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Leistung auswählen</p>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {(services as ServiceListItem[]).filter((s) => !s.is_base_service).map((service) => (
                  <button
                    key={service.id}
                    onClick={() => adjustServiceMutation.mutate(service.id)}
                    disabled={adjustServiceMutation.isPending}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left hover:bg-slate-100 disabled:opacity-50"
                  >
                    <p className="text-sm font-semibold text-slate-900">{service.name}</p>
                    <p className="mt-1 text-xs text-slate-500">{serviceTypeLabels[service.service_type]} · {service.tax_rate}%</p>
                  </button>
                ))}
                {(services as ServiceListItem[]).filter((s) => !s.is_base_service).length === 0 && (
                  <p className="text-sm text-slate-400 col-span-3">Keine weiteren Leistungen vorhanden. Bitte zuerst im <Link to={`/partners/${item.journal_line?.partner_id}/services`} className="text-blue-600 hover:underline">Partner-Service-Manager</Link> anlegen.</p>
                )}
              </div>
            </div>
          ) : isServiceTypeReview ? (
            <>
              <button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending} className="rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50">
                Freigeben
              </button>
              <button onClick={() => setMode('type-adjust')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">
                Typ korrigieren
              </button>
            </>
          ) : (
            <>
              <button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
                {item.item_type === 'service_assignment' ? 'Vorschlag übernehmen' : item.item_type === 'new_partner' ? 'Partner ist korrekt' : 'Bestätigen'}
              </button>
              {item.item_type === 'service_assignment' ? (
                <>
                  <button onClick={() => setMode('service-select')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Andere Leistung</button>
                  <button onClick={() => rejectMutation.mutate()} disabled={rejectMutation.isPending} className="rounded-xl border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50">Ablehnen</button>
                </>
              ) : (
                <>
                  <button onClick={() => setMode('reassign')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">
                    {item.item_type === 'new_partner' ? 'Anderen Partner zuweisen' : 'Anderer Partner'}
                  </button>
                  {item.item_type !== 'new_partner' && (
                    <button onClick={() => setMode('new-partner')} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Neuer Partner</button>
                  )}
                </>
              )}
            </>
          )}
        </div>
      ) : null}

      {mode === 'type-adjust' ? (
        <div className="mt-4 flex flex-wrap items-end gap-3 rounded-2xl bg-slate-50 p-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Typ</span>
            <select
              value={serviceTypeDraft}
              onChange={(e) => setServiceTypeDraft(e.target.value)}
              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            >
              {(['customer', 'supplier', 'employee', 'shareholder', 'authority', 'internal_transfer', 'unknown'] as const).map((t) => (
                <option key={t} value={t}>{serviceTypeLabels[t]}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Steuersatz (opt.)</span>
            <input
              value={taxRateDraft}
              onChange={(e) => setTaxRateDraft(e.target.value)}
              placeholder="z. B. 20.00"
              className="w-28 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            />
          </label>
          <label className="flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900">
            <input
              type="checkbox"
              checked={erfolgsneutralDraft}
              onChange={(e) => setErfolgsneutralDraft(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Erfolgsneutral
          </label>
          <button onClick={() => adjustTypeMutation.mutate()} disabled={adjustTypeMutation.isPending} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50">
            Speichern
          </button>
          <button onClick={() => setMode('idle')} className="text-xs font-semibold uppercase tracking-wide text-slate-400">Abbrechen</button>
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
    </article>
  )
}

function resolveCriterionLabel(reason?: string) {
  if (!reason) return 'kein Kriterium'
  if (reason.startsWith('keyword:')) return `Keyword: ${reason.replace('keyword:', '')}`
  if (reason === 'amount<=0') return 'Betrag negativ/null'
  if (reason === 'amount>0') return 'Betrag positiv'
  return reason.replaceAll('_', ' ')
}

function resolveHeadline(item: ReviewItem) {
  if (item.item_type === 'service_assignment') {
    return item.journal_line?.partner_name ?? item.journal_line?.partner_name_raw ?? 'Leistungs-Zuordnung prüfen'
  }
  if (item.item_type === 'service_type_review') {
    return item.service?.name ?? 'Leistungstyp prüfen'
  }
  if (item.item_type === 'new_partner') {
    return item.context.partner_name_raw ?? 'Neuen Partner prüfen'
  }
  if (item.item_type === 'manual_service_assignment') {
    return item.journal_line?.partner_name ?? item.journal_line?.partner_name_raw ?? 'Leistung manuell zuordnen'
  }
  return item.context.partner_name_raw ?? item.journal_line?.partner_name_raw ?? 'Partner-Zuordnung prüfen'
}

function resolveCurrentState(item: ReviewItem) {
  if (item.item_type === 'service_assignment') {
    return item.context.current_service_name ?? 'Keine Leistung hinterlegt'
  }
  if (item.item_type === 'name_match_with_iban') {
    return 'Partner per Name zugeordnet'
  }
  if (item.item_type === 'service_type_review') {
    return serviceTypeLabels[item.context.previous_type ?? item.service?.service_type ?? 'unknown']
  }
  if (item.item_type === 'new_partner') {
    return 'Automatisch neu angelegt'
  }
  if (item.item_type === 'manual_service_assignment') {
    return 'Basisleistung'
  }
  return outcomeLabels[item.context.match_outcome ?? ''] ?? 'Automatische Zuordnung'
}

function resolveSuggestedState(item: ReviewItem) {
  if (item.item_type === 'service_assignment') {
    if (item.context.proposed_service_name) {
      return item.context.proposed_service_name
    }
    if (item.context.matching_service_names?.length) {
      return item.context.matching_service_names.join(', ')
    }
    return `${item.context.matching_services?.length ?? 0} mögliche Leistungen`
  }
  if (item.item_type === 'service_type_review') {
    const typeLabel = serviceTypeLabels[item.context.auto_assigned_type ?? 'unknown']
    const taxRate = item.context.auto_assigned_tax_rate ?? item.service?.tax_rate
    const erfolgsneutralLabel = item.service?.erfolgsneutral ? 'erfolgsneutral' : 'nicht erfolgsneutral'
    return taxRate != null ? `${typeLabel} · ${taxRate} % MwSt. · ${erfolgsneutralLabel}` : `${typeLabel} · ${erfolgsneutralLabel}`
  }
  if (item.item_type === 'new_partner') {
    return 'Prüfen – evtl. existiert dieser Partner bereits'
  }
  if (item.item_type === 'name_match_with_iban') {
    return item.journal_line?.partner_name ?? item.context.suggested_partner_name ?? 'Zuordnung manuell prüfen'
  }
  if (item.item_type === 'manual_service_assignment') {
    return 'Leistung manuell auswählen'
  }
  return item.context.suggested_partner_name ?? 'Partner manuell prüfen'
}

function IbanDeviationPanel({ item }: { item: ReviewItem }) {
  const diagnosis = item.context.diagnosis
  const ibanDiag = diagnosis?.iban
  const importRawIban = item.context.raw_iban ?? item.journal_line?.partner_iban_raw ?? item.context.partner_iban_raw
  const normalizedIban = ibanDiag?.normalized ?? (importRawIban ? importRawIban.replaceAll(' ', '').toUpperCase() : undefined)
  const knownIbans = item.context.matched_partner_ibans ?? []

  let statusDetail = 'Keine IBAN im Import vorhanden'
  if (ibanDiag?.provided) {
    if (ibanDiag.excluded) {
      statusDetail = 'IBAN ist als eigene Konto-IBAN ausgeschlossen'
    } else if (ibanDiag.matches_partner_iban) {
      statusDetail = 'IBAN ist beim zugeordneten Partner bereits vorhanden'
    } else {
      statusDetail = 'Für diese IBAN wurde kein Partner über den IBAN-Lookup gefunden'
    }
  }

  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">IBAN-Abweichung analysiert</p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <InfoTile
          title="Import-IBAN"
          body={importRawIban ?? 'Nicht vorhanden'}
          footer={normalizedIban ? `Normalisiert: ${normalizedIban}` : undefined}
        />
        <InfoTile
          title="IBAN-Prüfstatus"
          body={statusDetail}
          footer={knownIbans.length > 0 ? `${knownIbans.length} bekannte Partner-IBAN(s)` : 'Keine Partner-IBAN hinterlegt'}
        />
      </div>
      {knownIbans.length > 0 ? (
        <div className="mt-3 rounded-xl bg-white/80 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bekannte Partner-IBANs</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-700">
            {knownIbans.map((iban) => (
              <li key={iban} className="font-mono">
                {iban}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function InfoTile({ title, body, footer }: { title: string; body: string; footer?: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 text-sm font-semibold text-slate-900">{body}</p>
      {footer ? <div className="mt-1 text-sm text-slate-500">{footer}</div> : null}
    </div>
  )
}

function NoPartnerRawDataPanel({ context }: { context: ReviewItem['context'] }) {
  const entries: { label: string; value: string }[] = []
  if (context.raw_iban) entries.push({ label: 'IBAN (roh)', value: context.raw_iban })
  if (context.raw_account) entries.push({ label: 'Kontonummer (roh)', value: context.raw_account })
  if (context.raw_text) entries.push({ label: 'Buchungstext', value: context.raw_text })
  if (entries.length === 0) return null
  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">Verfügbare Daten – kein Treffer</p>
      <ul className="mt-2 space-y-1">
        {entries.map((e) => (
          <li key={e.label} className="flex items-start gap-2 text-sm">
            <span className="mt-0.5 shrink-0 text-amber-500">✕</span>
            <span>
              <span className="font-medium text-slate-800">{e.label}:</span>{' '}
              <span className="text-slate-600">{e.value}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function _noMatchReasonLabel(reason: string | undefined): string {
  const labels: Record<string, string> = {
    no_active_partners: 'Keine aktiven Partner vorhanden',
    no_services_configured: 'Keine Leistungen konfiguriert',
    no_matchers_configured: 'Keine Matcher konfiguriert',
  }
  return labels[reason ?? ''] ?? 'Keine Matcher vorhanden'
}

function NoPartnerDiagnosisPanel({ diagnosis }: { diagnosis: NoPartnerDiagnosis }) {
  const steps: { label: string; detail: string }[] = []

  const iban = diagnosis.iban
  if (iban) {
    let detail: string
    if (iban.provided && iban.excluded) {
      detail = `${iban.normalized} – als eigene Konto-IBAN ausgeschlossen`
    } else if (iban.provided) {
      detail = `${iban.normalized} – kein Partner gefunden`
    } else {
      detail = 'Keine IBAN im Import vorhanden'
    }
    steps.push({ label: 'IBAN', detail })
  }

  const account = diagnosis.account
  if (account) {
    let detail: string
    if (account.provided && account.excluded) {
      detail = `${account.normalized} – als eigene Kontonummer ausgeschlossen`
    } else if (account.provided) {
      detail = `${account.normalized} – kein Partner gefunden`
    } else {
      detail = 'Keine Kontonummer im Import vorhanden'
    }
    steps.push({ label: 'Kontonummer', detail })
  }

  const name = diagnosis.name
  if (name) {
    const detail = name.provided
      ? `„${name.value}“ – kein aktiver Partner gefunden`
      : 'Kein Partnername im Import vorhanden'
    steps.push({ label: 'Partnername', detail })
  }

  const sm = diagnosis.service_matchers
  if (sm) {
    let detail: string
    if (sm.skipped) {
      detail = 'Kein Buchungstext – Matcher nicht geprüft'
    } else if (sm.total_matchers === 0) {
      detail = _noMatchReasonLabel(sm.reason)
    } else {
      detail = `${sm.total_matchers} Matcher geprüft – kein Treffer`
    }
    steps.push({ label: 'Leistungs-Matcher', detail })
  }

  if (steps.length === 0) return null

  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">Geprüft – kein Treffer</p>
      <ul className="mt-2 space-y-1">
        {steps.map((step) => (
          <li key={step.label} className="flex items-start gap-2 text-sm">
            <span className="mt-0.5 shrink-0 text-amber-500">✕</span>
            <span>
              <span className="font-medium text-slate-800">{step.label}:</span>{' '}
              <span className="text-slate-600">{step.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
