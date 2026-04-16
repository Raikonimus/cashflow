import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import {
  getPartner,
  addPartnerIban,
  previewPartnerIban,
  deletePartnerIban,
  addPartnerAccount,
  previewPartnerAccount,
  deletePartnerAccount,
  addPartnerName,
  deletePartnerName,
  getPartnerNeighbors,
  updatePartnerDisplayName,
  deletePartner,
} from '@/api/partners'
import { listPartnerServices } from '@/api/services'
import type { ServiceListItem, ServiceType } from '@/api/services'
import type { AccountPreviewLineItem, PartnerAccount } from '@/api/partners'
import { listJournalLines } from '@/api/journal'
import { MergeDialog } from './MergeDialog'

const serviceTypeLabels: Record<ServiceType, string> = {
  customer: 'Kunde',
  supplier: 'Lieferant',
  employee: 'Mitarbeiter',
  shareholder: 'Gesellschafter',
  authority: 'Behörde',
  internal_transfer: 'Interne Umbuchung',
  unknown: 'Unbekannt',
}

export function PartnerDetailPage() {
  const { partnerId } = useParams<{ partnerId: string }>()
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const role = useAuthStore((s) => s.user?.role ?? '')
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [showMerge, setShowMerge] = useState(false)
  const [newIban, setNewIban] = useState('')
  const [newAccountNumber, setNewAccountNumber] = useState('')
  const [newBlz, setNewBlz] = useState('')
  const [newBic, setNewBic] = useState('')
  const [ibanPreview, setIbanPreview] = useState<AccountPreviewLineItem[] | null>(null)
  const [accountPreview, setAccountPreview] = useState<AccountPreviewLineItem[] | null>(null)
  const [newName, setNewName] = useState('')
  const [editingDisplayName, setEditingDisplayName] = useState(false)
  const [displayNameDraft, setDisplayNameDraft] = useState('')
  const [deleteNotice, setDeleteNotice] = useState<string | null>(null)

  const { data: partner, isLoading, isError } = useQuery({
    queryKey: ['partner', mandantId, partnerId],
    queryFn: () => getPartner(mandantId, partnerId!),
    enabled: !!mandantId && !!partnerId,
  })

  const { data: neighbors } = useQuery({
    queryKey: ['partner-neighbors', mandantId, partnerId],
    queryFn: () => getPartnerNeighbors(mandantId, partnerId!),
    enabled: !!mandantId && !!partnerId,
  })

  const { data: services = [] } = useQuery({
    queryKey: ['partner-services', mandantId, partnerId],
    queryFn: () => listPartnerServices(mandantId, partnerId!),
    enabled: !!mandantId && !!partnerId,
  })

  const isReadOnly = role === 'viewer'

  const addIbanMutation = useMutation({
    mutationFn: (reassign: boolean) => addPartnerIban(mandantId, partnerId!, newIban.trim(), reassign),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setNewIban('')
      setIbanPreview(null)
    },
  })

  const previewIbanMutation = useMutation({
    mutationFn: () => previewPartnerIban(mandantId, partnerId!, newIban.trim()),
    onSuccess: (data) => setIbanPreview(data.matched_lines),
  })

  const deleteIbanMutation = useMutation({
    mutationFn: (ibanId: string) => deletePartnerIban(mandantId, partnerId!, ibanId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] }),
  })

  const addAccountMutation = useMutation({
    mutationFn: (reassign: boolean) =>
      addPartnerAccount(mandantId, partnerId!, {
        account_number: newAccountNumber.trim(),
        blz: newBlz.trim() || undefined,
        bic: newBic.trim() || undefined,
      }, reassign),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setNewAccountNumber('')
      setNewBlz('')
      setNewBic('')
      setAccountPreview(null)
    },
  })

  const previewAccountMutation = useMutation({
    mutationFn: () =>
      previewPartnerAccount(mandantId, partnerId!, {
        account_number: newAccountNumber.trim(),
        blz: newBlz.trim() || undefined,
      }),
    onSuccess: (data) => setAccountPreview(data.matched_lines),
  })

  const deleteAccountMutation = useMutation({
    mutationFn: (accountId: string) => deletePartnerAccount(mandantId, partnerId!, accountId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] }),
  })

  const addNameMutation = useMutation({
    mutationFn: () => addPartnerName(mandantId, partnerId!, newName.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      setNewName('')
    },
  })

  const deleteNameMutation = useMutation({
    mutationFn: (nameId: string) => deletePartnerName(mandantId, partnerId!, nameId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] }),
  })

  const updateDisplayNameMutation = useMutation({
    mutationFn: (name: string | null) => updatePartnerDisplayName(mandantId, partnerId!, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setEditingDisplayName(false)
    },
  })

  const deletePartnerMutation = useMutation({
    mutationFn: () => deletePartner(mandantId, partnerId!),
    onSuccess: async () => {
      setDeleteNotice(null)
      await queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      navigate('/partners')
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setDeleteNotice('Partner kann nicht gelöscht werden. Verschiebe zuerst alle Buchungen auf einen anderen Partner.')
        return
      }
      setDeleteNotice('Partner konnte nicht gelöscht werden.')
    },
  })

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (isError || !partner) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">
        Partner nicht gefunden.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-2 flex items-center justify-between text-sm text-gray-400">
        <Link to="/partners" className="hover:underline">Partner</Link>
        {' / '}
        {partner.display_name ?? partner.name}
        <div className="flex gap-1">
          <button
            onClick={() => neighbors?.prev && navigate(`/partners/${neighbors.prev.id}`)}
            disabled={!neighbors?.prev}
            title={neighbors?.prev ? neighbors.prev.name : undefined}
            className="rounded border px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← Vorheriger
          </button>
          <button
            onClick={() => neighbors?.next && navigate(`/partners/${neighbors.next.id}`)}
            disabled={!neighbors?.next}
            title={neighbors?.next ? neighbors.next.name : undefined}
            className="rounded border px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Nächster →
          </button>
        </div>
      </div>

      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {partner.display_name ?? partner.name}
          </h1>
          {partner.display_name && (
            <p className="mt-0.5 text-xs text-gray-400">Interner Name: {partner.name}</p>
          )}
          {!partner.is_active && (
            <span className="text-xs text-gray-400">(inaktiv — gemergt)</span>
          )}
          {/* Anzeigename bearbeiten */}
          {!isReadOnly && partner.is_active && (
            editingDisplayName ? (
              <div className="mt-2 flex items-center gap-2">
                <input
                  autoFocus
                  value={displayNameDraft}
                  onChange={(e) => setDisplayNameDraft(e.target.value)}
                  placeholder={partner.name}
                  className="rounded border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  onClick={() => updateDisplayNameMutation.mutate(displayNameDraft.trim() || null)}
                  disabled={updateDisplayNameMutation.isPending}
                  className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  Speichern
                </button>
                {partner.display_name && (
                  <button
                    onClick={() => updateDisplayNameMutation.mutate(null)}
                    disabled={updateDisplayNameMutation.isPending}
                    className="rounded border px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
                  >
                    Zurücksetzen
                  </button>
                )}
                <button
                  onClick={() => setEditingDisplayName(false)}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  Abbrechen
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setDisplayNameDraft(partner.display_name ?? ''); setEditingDisplayName(true) }}
                className="mt-1 text-xs text-gray-400 hover:text-gray-600 hover:underline"
              >
                {partner.display_name ? 'Anzeigenamen ändern' : '+ Anzeigenamen vergeben'}
              </button>
            )
          )}
        </div>
        {!isReadOnly && partner.is_active && (
          <div className="flex gap-2">
            <button
              onClick={() => setShowMerge(true)}
              className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            >
              Merge…
            </button>
            <button
              onClick={() => {
                const confirmed = window.confirm('Partner wirklich löschen? Das ist nur möglich, wenn keine Buchungen mehr zugeordnet sind.')
                if (!confirmed) return
                setDeleteNotice(null)
                deletePartnerMutation.mutate()
              }}
              disabled={deletePartnerMutation.isPending}
              className="rounded border border-red-500 px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              Partner löschen
            </button>
          </div>
        )}
      </div>

      {deleteNotice && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {deleteNotice}
        </div>
      )}

      {/* IBANs */}
      <Section title="IBANs">
        {partner.ibans.length === 0 && (
          <p className="text-sm text-gray-400">Keine IBANs hinterlegt.</p>
        )}
        {partner.ibans.map((i) => (
          <ItemRow
            key={i.id}
            label={<code className="font-mono text-sm">{i.iban}</code>}
            onDelete={isReadOnly ? undefined : () => deleteIbanMutation.mutate(i.id)}
          />
        ))}
        {!isReadOnly && (
          <InlineAddIban
            iban={newIban}
            onIbanChange={(value) => {
              setNewIban(value)
              setIbanPreview(null)
            }}
            onPreview={() => previewIbanMutation.mutate()}
            previewLoading={previewIbanMutation.isPending}
            previewLines={ibanPreview}
            onSubmit={() => addIbanMutation.mutate(!!ibanPreview && ibanPreview.some((line) => !line.already_assigned))}
            loading={addIbanMutation.isPending}
            error={addIbanMutation.isError ? 'IBAN bereits vergeben oder ungültig.' : undefined}
          />
        )}
      </Section>

      {/* Kontonummern */}
      <Section title="Kontonummern">
        {partner.accounts.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Kontonummern hinterlegt.</p>
        ) : (
          partner.accounts.map((a: PartnerAccount) => (
            <ItemRow
              key={a.id}
              label={
                <span className="font-mono text-sm">
                  {a.account_number}
                  {a.blz && <span className="ml-2 text-xs text-gray-400">BLZ {a.blz}</span>}
                  {a.bic && <span className="ml-2 text-xs text-gray-400">{a.bic}</span>}
                </span>
              }
              onDelete={isReadOnly ? undefined : () => deleteAccountMutation.mutate(a.id)}
            />
          ))
        )}
        {!isReadOnly && (
          <InlineAddAccount
            accountNumber={newAccountNumber}
            blz={newBlz}
            bic={newBic}
            onAccountNumberChange={(v) => { setNewAccountNumber(v); setAccountPreview(null) }}
            onBlzChange={(v) => { setNewBlz(v); setAccountPreview(null) }}
            onBicChange={setNewBic}
            onPreview={() => previewAccountMutation.mutate()}
            previewLoading={previewAccountMutation.isPending}
            previewLines={accountPreview}
            onSubmit={() => addAccountMutation.mutate(!!accountPreview && accountPreview.some((l) => !l.already_assigned))}
            loading={addAccountMutation.isPending}
            error={addAccountMutation.isError ? 'Kontonummer bereits vergeben oder ungültig.' : undefined}
          />
        )}
      </Section>

      {/* Namen */}
      <Section title="Namensvarianten">
        {partner.names.length === 0 && (
          <p className="text-sm text-gray-400">Keine Namensvarianten hinterlegt.</p>
        )}
        {partner.names.map((n) => (
          <ItemRow
            key={n.id}
            label={n.name}
            onDelete={isReadOnly ? undefined : () => deleteNameMutation.mutate(n.id)}
          />
        ))}
        {!isReadOnly && (
          <InlineAdd
            value={newName}
            onChange={setNewName}
            placeholder="Namensvariante eingeben"
            onSubmit={() => addNameMutation.mutate()}
            loading={addNameMutation.isPending}
            error={addNameMutation.isError ? 'Name bereits vorhanden.' : undefined}
          />
        )}
      </Section>

      <Section title="Leistungen">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-sm text-gray-500">
            Leistungen und Geltungszeiträume werden in einer eigenen Verwaltungsansicht gepflegt.
          </p>
          <Link
            to={`/partners/${partnerId}/services`}
            className="rounded border border-blue-200 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50"
          >
            Leistungen verwalten
          </Link>
        </div>

        {(services as ServiceListItem[]).length === 0 ? (
          <p className="text-sm text-gray-400">Noch keine Leistungen hinterlegt.</p>
        ) : (
          <div className="space-y-2">
            {(services as ServiceListItem[]).map((service) => (
              <div key={service.id} className="rounded-lg border border-gray-100 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-gray-900">{service.name}</p>
                      {service.is_base_service && (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                          Basis
                        </span>
                      )}
                    </div>
                    {service.description && (
                      <p className="mt-1 text-sm text-gray-500">{service.description}</p>
                    )}
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    <div>Typ: {serviceTypeLabels[service.service_type]}</div>
                    <div>Steuer: {service.tax_rate}%</div>
                    <div>Matcher: {service.matchers?.length ?? 0}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {showMerge && (
        <MergeDialog
          sourcePartner={{ id: partner.id, name: partner.name }}
          onClose={() => setShowMerge(false)}
          onSuccess={() => {
            setShowMerge(false)
            navigate('/partners')
          }}
        />
      )}

      {/* Buchungszeilen */}
      <JournalSection mandantId={mandantId} partnerId={partner.id} />
    </div>
  )
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">{title}</h2>
      {children}
    </div>
  )
}

function ItemRow({
  label,
  onDelete,
}: {
  label: React.ReactNode
  onDelete?: () => void
}) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-gray-800">{label}</span>
      {onDelete && (
        <button
          onClick={onDelete}
          className="ml-3 rounded px-2 py-0.5 text-xs text-red-500 hover:bg-red-50"
        >
          Entfernen
        </button>
      )}
    </div>
  )
}

function InlineAdd({
  value,
  onChange,
  placeholder,
  onSubmit,
  loading,
  error,
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  onSubmit: () => void
  loading: boolean
  error?: string
}) {
  return (
    <div className="mt-3">
      <div className="flex gap-2">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && value.trim() && onSubmit()}
          placeholder={placeholder}
          className="flex-1 rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={onSubmit}
          disabled={!value.trim() || loading}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Hinzufügen
        </button>
      </div>
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  )
}

function InlineAddIban({
  iban,
  onIbanChange,
  onPreview,
  previewLoading,
  previewLines,
  onSubmit,
  loading,
  error,
}: {
  iban: string
  onIbanChange: (v: string) => void
  onPreview: () => void
  previewLoading: boolean
  previewLines: AccountPreviewLineItem[] | null
  onSubmit: () => void
  loading: boolean
  error?: string
}) {
  const canAct = iban.trim().length > 0 && !loading && !previewLoading
  const canSubmit = canAct && previewLines !== null

  return (
    <div className="mt-3 space-y-2">
      <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto]">
        <input
          aria-label="IBAN"
          value={iban}
          onChange={(e) => onIbanChange(e.target.value)}
          placeholder="IBAN eingeben (z. B. DE89...)"
          className="rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={onPreview}
          disabled={!canAct}
          className="rounded border border-blue-300 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
        >
          {previewLoading ? '…' : 'Testen'}
        </button>
        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '…' : 'Hinzufügen'}
        </button>
      </div>

      {previewLines !== null && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          {previewLines.length === 0 ? (
            <p className="text-xs text-gray-700">Keine passenden Buchungszeilen gefunden.</p>
          ) : (
            <>
              {(() => {
                const foreign = previewLines.filter((line) => !line.already_assigned)
                const own = previewLines.filter((line) => line.already_assigned)
                return (
                  <>
                    {foreign.length > 0 && (
                      <p className="mb-2 text-xs font-semibold text-gray-700">
                        {foreign.length} Buchungszeile{foreign.length !== 1 ? 'n' : ''} anderer Partner passen -
                        {' '}werden beim Hinzufügen diesem Partner zugeordnet:
                      </p>
                    )}
                    {own.length > 0 && (
                      <p className="mb-2 text-xs font-semibold text-gray-700">
                        {own.length} Buchungszeile{own.length !== 1 ? 'n' : ''} bereits diesem Partner zugeordnet.
                      </p>
                    )}
                    <div className="mt-2 overflow-x-auto rounded border border-gray-200 bg-white">
                      <table className="min-w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Hinweis</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Datum</th>
                            <th className="px-3 py-2 text-right font-semibold text-gray-500">Betrag</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Text</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Leistung</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Aktueller Partner</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Buchungsname</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {[...previewLines]
                            .sort((a, b) => Number(b.has_conflicting_partner_criteria) - Number(a.has_conflicting_partner_criteria))
                            .map((line) => {
                            let rowClassName = 'hover:bg-gray-50'
                            if (line.has_conflicting_partner_criteria) {
                              rowClassName = 'bg-red-50/40 hover:bg-red-50'
                            } else if (line.already_assigned) {
                              rowClassName = 'bg-gray-50 text-gray-500'
                            }
                            return (
                            <tr key={line.journal_line_id} className={rowClassName}>
                              <td className="whitespace-nowrap px-3 py-2">
                                {line.has_conflicting_partner_criteria ? (
                                  <span className="rounded bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-700" title={line.conflicting_partner_criteria.join(', ')}>
                                    Widerspruch
                                  </span>
                                ) : (
                                  <span className="font-semibold text-green-700" title="Kein Widerspruch">✓</span>
                                )}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2 text-gray-700">{line.booking_date}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-gray-700">
                                {Number(line.amount).toLocaleString('de-DE', { style: 'currency', currency: line.currency })}
                              </td>
                              <td className="max-w-[220px] truncate px-3 py-2 text-gray-600">{line.text ?? '–'}</td>
                              <td className="px-3 py-2 text-gray-700">{line.current_service_name ?? '–'}</td>
                              <td className="px-3 py-2 text-gray-700">{line.current_partner_name ?? '–'}</td>
                              <td className="px-3 py-2 text-gray-500">{line.partner_name_raw ?? '–'}</td>
                            </tr>
                          )})}
                        </tbody>
                      </table>
                    </div>
                  </>
                )
              })()}
            </>
          )}
        </div>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

function InlineAddAccount({
  accountNumber,
  blz,
  bic,
  onAccountNumberChange,
  onBlzChange,
  onBicChange,
  onPreview,
  previewLoading,
  previewLines,
  onSubmit,
  loading,
  error,
}: {
  accountNumber: string
  blz: string
  bic: string
  onAccountNumberChange: (v: string) => void
  onBlzChange: (v: string) => void
  onBicChange: (v: string) => void
  onPreview: () => void
  previewLoading: boolean
  previewLines: AccountPreviewLineItem[] | null
  onSubmit: () => void
  loading: boolean
  error?: string
}) {
  const canAct = accountNumber.trim().length > 0 && !loading && !previewLoading
  const canSubmit = canAct && previewLines !== null

  return (
    <div className="mt-3 space-y-2">
      <div className="grid gap-2 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
        <input
          aria-label="Kontonummer"
          value={accountNumber}
          onChange={(e) => onAccountNumberChange(e.target.value)}
          placeholder="Kontonummer"
          className="rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          aria-label="BLZ"
          value={blz}
          onChange={(e) => onBlzChange(e.target.value)}
          placeholder="BLZ"
          className="rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          aria-label="BIC"
          value={bic}
          onChange={(e) => onBicChange(e.target.value)}
          placeholder="BIC"
          className="rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={onPreview}
          disabled={!canAct}
          className="rounded border border-blue-300 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
        >
          {previewLoading ? '…' : 'Testen'}
        </button>
        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '…' : 'Hinzufügen'}
        </button>
      </div>

      {previewLines !== null && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          {previewLines.length === 0 ? (
            <p className="text-xs text-gray-700">Keine passenden Buchungszeilen gefunden.</p>
          ) : (
            <>
              {(() => {
                const foreign = previewLines.filter((l) => !l.already_assigned)
                const own = previewLines.filter((l) => l.already_assigned)
                return (
                  <>
                    {foreign.length > 0 && (
                      <p className="mb-2 text-xs font-semibold text-gray-700">
                        {foreign.length} Buchungszeile{foreign.length !== 1 ? 'n' : ''} anderer Partner passen –
                        {' '}werden beim Hinzufügen diesem Partner zugeordnet:
                      </p>
                    )}
                    {own.length > 0 && (
                      <p className="mb-2 text-xs font-semibold text-gray-700">
                        {own.length} Buchungszeile{own.length !== 1 ? 'n' : ''} bereits diesem Partner zugeordnet.
                      </p>
                    )}
                    <div className="mt-2 overflow-x-auto rounded border border-gray-200 bg-white">
                      <table className="min-w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Hinweis</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Datum</th>
                            <th className="px-3 py-2 text-right font-semibold text-gray-500">Betrag</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Text</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Leistung</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Aktueller Partner</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500">Buchungsname</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {[...previewLines]
                            .sort((a, b) => Number(b.has_conflicting_partner_criteria) - Number(a.has_conflicting_partner_criteria))
                            .map((l) => {
                            let rowClassName = 'hover:bg-gray-50'
                            if (l.has_conflicting_partner_criteria) {
                              rowClassName = 'bg-red-50/40 hover:bg-red-50'
                            } else if (l.already_assigned) {
                              rowClassName = 'bg-gray-50 text-gray-500'
                            }
                            return (
                            <tr key={l.journal_line_id} className={rowClassName}>
                              <td className="whitespace-nowrap px-3 py-2">
                                {l.has_conflicting_partner_criteria ? (
                                  <span className="rounded bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-700" title={l.conflicting_partner_criteria.join(', ')}>
                                    Widerspruch
                                  </span>
                                ) : (
                                  <span className="font-semibold text-green-700" title="Kein Widerspruch">✓</span>
                                )}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2 text-gray-700">{l.booking_date}</td>
                              <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-gray-700">
                                {Number(l.amount).toLocaleString('de-DE', { style: 'currency', currency: l.currency })}
                              </td>
                              <td className="max-w-[220px] truncate px-3 py-2 text-gray-600">{l.text ?? '–'}</td>
                              <td className="px-3 py-2 text-gray-700">{l.current_service_name ?? '–'}</td>
                              <td className="px-3 py-2 text-gray-700">{l.current_partner_name ?? '–'}</td>
                              <td className="px-3 py-2 text-gray-500">{l.partner_name_raw ?? '–'}</td>
                            </tr>
                          )})}
                        </tbody>
                      </table>
                    </div>
                  </>
                )
              })()}
            </>
          )}
        </div>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

// ─── Journal Section ──────────────────────────────────────────────────────────

const PAGE_SIZE = 25

type JournalSortField = 'valuta_date' | 'booking_date' | 'amount' | 'text' | 'service_name'

function JournalSection({ mandantId, partnerId }: { mandantId: string; partnerId: string }) {
  const sentinelRef = useRef<HTMLDivElement>(null)
  const [sortBy, setSortBy] = useState<JournalSortField>('valuta_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  function toggleSort(field: JournalSortField) {
    if (sortBy === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(field)
      setSortDir('desc')
    }
  }

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: ['partner-journal', mandantId, partnerId, sortBy, sortDir],
    queryFn: ({ pageParam = 1 }) =>
      listJournalLines(mandantId, { partner_id: partnerId, page: pageParam as number, size: PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page < lastPage.pages ? lastPage.page + 1 : undefined,
    enabled: !!mandantId && !!partnerId,
  })

  useEffect(() => {
    if (!sentinelRef.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { threshold: 0.1 },
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const lines = data?.pages.flatMap((p) => p.items) ?? []
  const total = data?.pages[0]?.total ?? 0

  function SortTh({ field, label, align = 'left' }: { field: JournalSortField; label: string; align?: 'left' | 'right' }) {
    const active = sortBy === field
    return (
      <th
        className={`cursor-pointer select-none px-4 py-2 text-${align} hover:bg-gray-100`}
        onClick={() => toggleSort(field)}
      >
        {label}
        {active ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
      </th>
    )
  }

  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Buchungszeilen
        </h2>
        {total > 0 && (
          <span className="text-xs text-gray-400">{total} gesamt</span>
        )}
      </div>

      {isLoading && (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      )}

      {!isLoading && lines.length === 0 && (
        <p className="px-5 py-6 text-center text-sm text-gray-400">
          Keine Buchungszeilen für diesen Partner.
        </p>
      )}

      {lines.length > 0 && (
        <table className="w-full table-fixed text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <SortTh field="valuta_date" label="Valuta" />
              <th className="w-[48%] px-4 py-2 text-left cursor-pointer select-none hover:bg-gray-100" onClick={() => toggleSort('text')}>
                Text{sortBy === 'text' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
              </th>
              <th className="w-[22%] px-4 py-2 text-left cursor-pointer select-none hover:bg-gray-100" onClick={() => toggleSort('service_name')}>
                Leistung{sortBy === 'service_name' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
              </th>
              <SortTh field="amount" label="Betrag" align="right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {lines.map((line) => (
              <tr key={line.id} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono text-xs text-gray-500 whitespace-nowrap">
                  {line.valuta_date}
                </td>
                <td className="px-4 py-2 text-gray-700">
                  <div className="line-clamp-2 break-words">
                  {line.text ?? line.partner_name_raw ?? <em className="text-gray-400">—</em>}
                  </div>
                </td>
                <td className="px-4 py-2 text-sm text-gray-600">
                  {line.service_name ?? <span className="text-xs text-gray-400">—</span>}
                </td>
                <td className={`px-4 py-2 text-right font-mono text-sm whitespace-nowrap ${
                  Number(line.amount) < 0 ? 'text-red-600' : 'text-green-700'
                }`}>
                  {Number(line.amount).toLocaleString('de-DE', {
                    style: 'currency',
                    currency: line.currency,
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Scroll-Sentinel */}
      <div ref={sentinelRef} className="py-2 text-center">
        {isFetchingNextPage && (
          <div className="inline-block h-5 w-5 animate-spin rounded-full border-4 border-blue-400 border-t-transparent" />
        )}
        {!hasNextPage && lines.length > 0 && (
          <p className="text-xs text-gray-300">Alle {total} Zeilen geladen</p>
        )}
      </div>
    </div>
  )
}
