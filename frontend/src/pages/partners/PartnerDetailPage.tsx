import { useState, useEffect, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import {
  getPartner,
  addPartnerIban,
  deletePartnerIban,
  addPartnerName,
  deletePartnerName,
  addPartnerPattern,
  deletePartnerPattern,
  getPartnerNeighbors,
  mergePartners,
  previewPattern,
  updatePartnerDisplayName,
} from '@/api/partners'
import type { PartnerPattern, PartnerAccount, PartnerNeighbor } from '@/api/partners'
import { listJournalLines } from '@/api/journal'
import { MergeDialog } from './MergeDialog'

export function PartnerDetailPage() {
  const { partnerId } = useParams<{ partnerId: string }>()
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const role = useAuthStore((s) => s.user?.role ?? '')
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [showMerge, setShowMerge] = useState(false)
  const [newIban, setNewIban] = useState('')
  const [newName, setNewName] = useState('')
  const [newPattern, setNewPattern] = useState('')
  const [patternType, setPatternType] = useState<'string' | 'regex'>('string')
  const [matchField, setMatchField] = useState<'partner_name' | 'partner_iban' | 'description'>('partner_name')
  const [editingDisplayName, setEditingDisplayName] = useState(false)
  const [displayNameDraft, setDisplayNameDraft] = useState('')

  // Pattern preview (live debounced + persisted after save)
  type PreviewQuery = { pattern: string; patternType: 'string' | 'regex'; matchField: 'partner_name' | 'partner_iban' | 'description' }
  const [livePreviewQuery, setLivePreviewQuery] = useState<PreviewQuery | null>(null)
  const [savedPreviewQuery, setSavedPreviewQuery] = useState<PreviewQuery | null>(null)
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const lastPatternSnapshot = useRef<PreviewQuery | null>(null)

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

  // Debounce pattern input → live preview
  useEffect(() => {
    clearTimeout(previewTimerRef.current)
    if (!newPattern.trim()) {
      setLivePreviewQuery(null)
      return
    }
    setSavedPreviewQuery(null)
    previewTimerRef.current = setTimeout(() => {
      setLivePreviewQuery({ pattern: newPattern.trim(), patternType, matchField })
    }, 350)
    return () => clearTimeout(previewTimerRef.current)
  }, [newPattern, patternType, matchField])

  const activePreview = savedPreviewQuery ?? livePreviewQuery

  const { data: previewResults, isFetching: previewFetching } = useQuery({
    queryKey: ['pattern-preview', mandantId, partnerId, activePreview],
    queryFn: () => previewPattern(mandantId, partnerId!, activePreview!.pattern, activePreview!.patternType, activePreview!.matchField),
    enabled: !!activePreview && !!mandantId && !!partnerId,
    staleTime: 15_000,
  })

  const isReadOnly = role === 'viewer'

  const addIbanMutation = useMutation({
    mutationFn: () => addPartnerIban(mandantId, partnerId!, newIban.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      setNewIban('')
    },
  })

  const deleteIbanMutation = useMutation({
    mutationFn: (ibanId: string) => deletePartnerIban(mandantId, partnerId!, ibanId),
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

  const addPatternMutation = useMutation({
    mutationFn: () =>
      addPartnerPattern(mandantId, partnerId!, {
        pattern: newPattern.trim(),
        pattern_type: patternType,
        match_field: matchField,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      if (lastPatternSnapshot.current) {
        setSavedPreviewQuery(lastPatternSnapshot.current)
      }
      setNewPattern('')
    },
  })

  const mergeIntoCurrentMutation = useMutation({
    mutationFn: (sourceId: string) => mergePartners(mandantId, sourceId, partnerId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['partner-neighbors', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['pattern-preview', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['partner-journal', mandantId, partnerId] })
    },
  })

  const updateDisplayNameMutation = useMutation({
    mutationFn: (name: string | null) => updatePartnerDisplayName(mandantId, partnerId!, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] })
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setEditingDisplayName(false)
    },
  })

  const deletePatternMutation = useMutation({
    mutationFn: (patternId: string) => deletePartnerPattern(mandantId, partnerId!, patternId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['partner', mandantId, partnerId] }),
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
          <button
            onClick={() => setShowMerge(true)}
            className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
          >
            Merge…
          </button>
        )}
      </div>

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
          <InlineAdd
            value={newIban}
            onChange={setNewIban}
            placeholder="IBAN eingeben (z. B. DE89…)"
            onSubmit={() => addIbanMutation.mutate()}
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
            />
          ))
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

      {/* Muster */}
      <Section title="Match-Muster">
        {partner.patterns.length === 0 && (
          <p className="text-sm text-gray-400">Keine Muster hinterlegt.</p>
        )}
        {partner.patterns.map((p: PartnerPattern) => (
          <ItemRow
            key={p.id}
            label={
              <span>
                <code className="font-mono text-sm">{p.pattern}</code>
                <span className="ml-2 text-xs text-gray-400">
                  [{p.pattern_type}] @ {p.match_field}
                </span>
              </span>
            }
            onDelete={isReadOnly ? undefined : () => deletePatternMutation.mutate(p.id)}
          />
        ))}
        {!isReadOnly && (
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              value={newPattern}
              onChange={(e) => setNewPattern(e.target.value)}
              placeholder="Muster eingeben"
              className="flex-1 rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={patternType}
              onChange={(e) => setPatternType(e.target.value as 'string' | 'regex')}
              className="rounded border px-2 py-1.5 text-sm"
            >
              <option value="string">String</option>
              <option value="regex">Regex</option>
            </select>
            <select
              value={matchField}
              onChange={(e) =>
                setMatchField(e.target.value as 'partner_name' | 'partner_iban' | 'description')
              }
              className="rounded border px-2 py-1.5 text-sm"
            >
              <option value="partner_name">Partnername</option>
              <option value="partner_iban">Partner-IBAN</option>
              <option value="description">Beschreibung</option>
            </select>
            <button
              onClick={() => {
                lastPatternSnapshot.current = { pattern: newPattern.trim(), patternType, matchField }
                addPatternMutation.mutate()
              }}
              disabled={!newPattern.trim() || addPatternMutation.isPending}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}
        {addPatternMutation.isError && (
          <p className="mt-1 text-xs text-red-500">
            Ungültiges Muster oder Muster bereits vorhanden.
          </p>
        )}
        {/* Muster-Vorschau */}
        {activePreview && (
          <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-blue-700">
                Vorschau matchende Partner
                {savedPreviewQuery && (
                  <span className="ml-2 font-normal text-green-700">(Muster gespeichert)</span>
                )}
              </span>
              {previewFetching && (
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
              )}
            </div>
            {!previewFetching && previewResults?.length === 0 && (
              <p className="text-xs text-gray-400">Keine anderen Partner matchen.</p>
            )}
            {activePreview.matchField === 'description' && (
              <p className="text-xs text-gray-400">Vorschau für Beschreibung nicht verfügbar.</p>
            )}
            {previewResults && previewResults.length > 0 && (
              <ul className="space-y-1.5">
                {previewResults.map((p: PartnerNeighbor) => (
                  <li key={p.id} className="flex items-center justify-between">
                    <Link
                      to={`/partners/${p.id}`}
                      className="text-sm text-blue-800 hover:underline"
                    >
                      {p.name}
                    </Link>
                    {!isReadOnly && (
                      <button
                        onClick={() => mergeIntoCurrentMutation.mutate(p.id)}
                        disabled={mergeIntoCurrentMutation.isPending}
                        className="rounded border border-orange-300 px-2 py-0.5 text-xs text-orange-700 hover:bg-orange-50 disabled:opacity-40"
                      >
                        → hierher mergen
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
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

// ─── Journal Section ──────────────────────────────────────────────────────────

const PAGE_SIZE = 25

function JournalSection({ mandantId, partnerId }: { mandantId: string; partnerId: string }) {
  const sentinelRef = useRef<HTMLDivElement>(null)

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: ['partner-journal', mandantId, partnerId],
    queryFn: ({ pageParam = 1 }) =>
      listJournalLines(mandantId, { partner_id: partnerId, page: pageParam as number, size: PAGE_SIZE }),
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
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2 text-left">Valuta</th>
              <th className="px-4 py-2 text-left">Text</th>
              <th className="px-4 py-2 text-right">Betrag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {lines.map((line) => (
              <tr key={line.id} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono text-xs text-gray-500 whitespace-nowrap">
                  {line.valuta_date}
                </td>
                <td className="max-w-xs truncate px-4 py-2 text-gray-700">
                  {line.text ?? line.partner_name_raw ?? <em className="text-gray-400">—</em>}
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
