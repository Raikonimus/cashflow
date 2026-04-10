import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { adjustReviewItem, confirmReviewItem, getReviewItem, listReviewItems } from '@/api/review'
import { EmptyReviewState, formatCurrency, formatReviewReason, InlineNotice, ReviewSubnav, reviewTypeLabels, serviceTypeLabels } from './reviewShared'

const serviceTypeOptions = ['customer', 'supplier', 'employee', 'authority', 'unknown'] as const

export function ServiceTypeReviewPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string>('')
  const [serviceTypeDraft, setServiceTypeDraft] = useState<string>('unknown')
  const [taxRateDraft, setTaxRateDraft] = useState<string>('')
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const { data: queue } = useQuery({
    queryKey: ['review', mandantId, 'service-types'],
    queryFn: () => listReviewItems(mandantId, { status: 'open', itemType: 'service_type_review', size: 100 }),
    enabled: !!mandantId,
  })

  useEffect(() => {
    const firstItem = queue?.items[0]?.id ?? ''
    setSelectedId((current) => (current && queue?.items.some((item) => item.id === current) ? current : firstItem))
  }, [queue])

  const { data: selectedItem } = useQuery({
    queryKey: ['review-item', mandantId, selectedId],
    queryFn: () => getReviewItem(mandantId, selectedId),
    enabled: !!mandantId && !!selectedId,
  })

  useEffect(() => {
    if (!selectedItem) return
    setServiceTypeDraft(selectedItem.context.auto_assigned_type ?? selectedItem.service?.service_type ?? 'unknown')
    setTaxRateDraft(selectedItem.service?.tax_rate ?? '')
  }, [selectedItem])

  const refreshAll = async (message: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['review'] }),
      queryClient.invalidateQueries({ queryKey: ['review-item', mandantId] }),
    ])
    setNotice({ tone: 'success', message })
  }

  const approveMutation = useMutation({
    mutationFn: () => confirmReviewItem(mandantId, selectedId),
    onSuccess: async () => refreshAll('Leistungstyp wurde freigegeben.'),
    onError: () => setNotice({ tone: 'error', message: 'Freigabe konnte nicht gespeichert werden.' }),
  })

  const adjustMutation = useMutation({
    mutationFn: () => adjustReviewItem(mandantId, selectedId, { service_type: serviceTypeDraft, tax_rate: taxRateDraft || undefined }),
    onSuccess: async () => refreshAll('Leistungstyp wurde korrigiert.'),
    onError: () => setNotice({ tone: 'error', message: 'Korrektur konnte nicht gespeichert werden.' }),
  })

  const items = queue?.items ?? []

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Review</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Leistungstyp-Prüfungen</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
          Automatisch gesetzte Leistungstypen mit allen aktuell zugeordneten Buchungszeilen freigeben oder korrigieren.
        </p>
      </div>

      <ReviewSubnav typeCount={items.length} />
      {notice ? <InlineNotice tone={notice.tone} message={notice.message} /> : null}

      {items.length === 0 ? (
        <EmptyReviewState
          title="Keine offenen Typ-Prüfungen"
          text="Sobald eine automatische Typ-Erkennung deine Freigabe braucht, erscheint sie hier mit allen betroffenen Buchungszeilen."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <aside className="space-y-3">
            {items.map((item) => {
              const isActive = item.id === selectedId
              return (
                <button
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  className={`w-full rounded-[1.5rem] border px-4 py-4 text-left shadow-sm transition ${isActive ? 'border-teal-500 bg-teal-50' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{item.service?.name ?? 'Unbenannte Leistung'}</p>
                      <p className="mt-1 text-xs uppercase tracking-wide text-slate-400">{reviewTypeLabels[item.item_type] ?? item.item_type}</p>
                    </div>
                    {item.service?.service_type_manual ? (
                      <span className="rounded-full bg-slate-200 px-2 py-1 text-[11px] font-semibold text-slate-700">manuell</span>
                    ) : null}
                  </div>
                  <p className="mt-3 text-sm text-slate-600">
                    Auto-Typ: <span className="font-medium text-slate-900">{serviceTypeLabels[item.context.auto_assigned_type ?? 'unknown']}</span>
                  </p>
                  <p className="mt-1 text-sm text-slate-500">{formatReviewReason(item.context.reason)}</p>
                  <p className="mt-3 text-xs text-slate-400">{item.assigned_journal_lines.length} zugeordnete Buchungszeilen</p>
                </button>
              )
            })}
          </aside>

          {selectedItem ? (
            <section className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-600">{reviewTypeLabels[selectedItem.item_type] ?? selectedItem.item_type}</p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-900">{selectedItem.service?.name ?? 'Leistung'}</h2>
                  <p className="mt-2 text-sm text-slate-500">{formatReviewReason(selectedItem.context.reason)}</p>
                </div>
                <div className="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-600">
                  <div>Aktuell: <span className="font-semibold text-slate-900">{serviceTypeLabels[selectedItem.context.previous_type ?? selectedItem.service?.service_type ?? 'unknown']}</span></div>
                  <div className="mt-1">Automatisch: <span className="font-semibold text-slate-900">{serviceTypeLabels[selectedItem.context.auto_assigned_type ?? 'unknown']}</span></div>
                </div>
              </div>

              <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Buchungszeilen</h3>
                  <div className="mt-3 space-y-3">
                    {selectedItem.assigned_journal_lines.map((line) => (
                      <article key={line.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{line.partner_name_raw ?? 'Ohne Partnername'}</p>
                            <p className="mt-1 text-sm text-slate-500">{line.text ?? 'Kein Buchungstext vorhanden'}</p>
                          </div>
                          <div className="text-right text-sm">
                            <p className="font-semibold text-slate-900">{formatCurrency(line.amount, line.currency)}</p>
                            <p className="mt-1 text-slate-400">{line.booking_date}</p>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>

                <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Aktionen</h3>
                  <button
                    onClick={() => approveMutation.mutate()}
                    disabled={approveMutation.isPending}
                    className="mt-4 w-full rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
                  >
                    Freigeben
                  </button>

                  <div className="mt-5 space-y-3 rounded-2xl bg-white p-4 ring-1 ring-slate-200">
                    <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Typ korrigieren
                      <select
                        value={serviceTypeDraft}
                        onChange={(event) => setServiceTypeDraft(event.target.value)}
                        className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                      >
                        {serviceTypeOptions.map((option) => (
                          <option key={option} value={option}>{serviceTypeLabels[option]}</option>
                        ))}
                      </select>
                    </label>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Steuersatz optional
                      <input
                        value={taxRateDraft}
                        onChange={(event) => setTaxRateDraft(event.target.value)}
                        placeholder="z. B. 20.00"
                        className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                      />
                    </label>
                    <button
                      onClick={() => adjustMutation.mutate()}
                      disabled={adjustMutation.isPending}
                      className="w-full rounded-xl border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                    >
                      Korrigieren
                    </button>
                  </div>
                </div>
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  )
}