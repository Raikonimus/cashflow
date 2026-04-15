import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuthStore } from '@/store/auth-store'
import { listPartners, createPartner, deletePartner, type PartnerListItem, type PartnerSortField, type SortDirection } from '@/api/partners'
import type { ServiceType } from '@/api/services'
import { BulkMergeDialog } from './BulkMergeDialog'

const serviceTypeBadges: Record<
  'customer' | 'supplier' | 'employee' | 'shareholder' | 'authority' | 'internal_transfer' | 'unknown',
  { label: string; short: string; className: string }
> = {
  customer: { label: 'Kunde', short: 'K', className: 'bg-emerald-100 text-emerald-700' },
  supplier: { label: 'Lieferant', short: 'L', className: 'bg-sky-100 text-sky-700' },
  employee: { label: 'Mitarbeiter', short: 'M', className: 'bg-amber-100 text-amber-700' },
  shareholder: { label: 'Gesellschafter', short: 'G', className: 'bg-rose-100 text-rose-700' },
  authority: { label: 'Behörde', short: 'B', className: 'bg-violet-100 text-violet-700' },
  internal_transfer: { label: 'Interne Umbuchung', short: 'U', className: 'bg-teal-100 text-teal-700' },
  unknown: { label: 'Unbekannt', short: '?', className: 'bg-slate-200 text-slate-700' },
}

export function PartnersPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [serviceTypeFilter, setServiceTypeFilter] = useState<ServiceType | ''>('')
  const [sortBy, setSortBy] = useState<PartnerSortField>('name')
  const [sortDir, setSortDir] = useState<SortDirection>('asc')
  const [showForm, setShowForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [selectedPartners, setSelectedPartners] = useState<Map<string, PartnerListItem>>(new Map())
  const [showBulkMerge, setShowBulkMerge] = useState(false)
  const [bulkDeleteError, setBulkDeleteError] = useState<string | null>(null)
  const role = useAuthStore((s) => s.user?.role ?? '')
  const queryClient = useQueryClient()

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ['partners', mandantId, page, showInactive, search, serviceTypeFilter, sortBy, sortDir],
    queryFn: () => listPartners(mandantId, page, 30, showInactive, search.trim(), serviceTypeFilter || undefined, sortBy, sortDir),
    placeholderData: (previousData) => previousData,
    enabled: !!mandantId,
  })

  const toggleSort = (field: PartnerSortField) => {
    setPage(1)
    if (sortBy === field) {
      setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortBy(field)
    setSortDir('asc')
  }

  const createMutation = useMutation({
    mutationFn: () => createPartner(mandantId, newName.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setNewName('')
      setShowForm(false)
    },
  })

  const isReadOnly = role === 'viewer'
  const currentPageIds = data?.items.map((p) => p.id) ?? []
  const allOnPageSelected =
    currentPageIds.length > 0 && currentPageIds.every((id) => selectedPartners.has(id))
  const someOnPageSelected = currentPageIds.some((id) => selectedPartners.has(id))

  function toggleSelect(p: PartnerListItem) {
    setSelectedPartners((prev) => {
      const next = new Map(prev)
      if (next.has(p.id)) next.delete(p.id)
      else next.set(p.id, p)
      return next
    })
  }

  function toggleSelectAll() {
    setSelectedPartners((prev) => {
      const next = new Map(prev)
      const items = data?.items ?? []
      if (allOnPageSelected) {
        items.forEach((p) => next.delete(p.id))
      } else {
        items.forEach((p) => next.set(p.id, p))
      }
      return next
    })
  }

  const bulkDeleteMutation = useMutation({
    mutationFn: async () => {
      const failed: string[] = []
      for (const [id, p] of selectedPartners) {
        try {
          await deletePartner(mandantId, id)
        } catch {
          failed.push(p.display_name ?? p.name)
        }
      }
      if (failed.length > 0) {
        throw new Error(
          `Folgende Partner konnten nicht gelöscht werden: ${failed.join(', ')}`,
        )
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setSelectedPartners(new Map())
      setBulkDeleteError(null)
    },
    onError: (err) => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setSelectedPartners(new Map())
      setBulkDeleteError(err instanceof Error ? err.message : 'Fehler beim Löschen.')
    },
  })

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center text-red-500">
        Fehler beim Laden der Partner.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Partner</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {showForm ? 'Abbrechen' : '+ Neuer Partner'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (newName.trim()) createMutation.mutate()
          }}
          className="mb-4 flex gap-2"
        >
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Partnername"
            className="flex-1 rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={!newName.trim() || createMutation.isPending}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Anlegen
          </button>
        </form>
      )}

      {selectedPartners.size > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
          <span className="text-sm font-medium text-blue-800">
            {selectedPartners.size} Partner ausgewählt
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedPartners(new Map())}
              className="rounded px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100"
            >
              Auswahl aufheben
            </button>
            {!isReadOnly && (
              <>
                <button
                  onClick={() => setShowBulkMerge(true)}
                  className="rounded border border-orange-300 px-3 py-1.5 text-sm text-orange-700 hover:bg-orange-50"
                >
                  Zusammenführen…
                </button>
                <button
                  onClick={() => {
                    if (globalThis.confirm(`${selectedPartners.size} Partner wirklich löschen?`))
                      bulkDeleteMutation.mutate()
                  }}
                  disabled={bulkDeleteMutation.isPending}
                  className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {bulkDeleteMutation.isPending ? 'Wird gelöscht…' : 'Löschen'}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {bulkDeleteError && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {bulkDeleteError}
          <button
            onClick={() => setBulkDeleteError(null)}
            className="ml-3 text-amber-700 hover:underline"
          >
            Schließen
          </button>
        </div>
      )}

      <div className="mb-4 flex items-center gap-4">
        <div className="relative flex-1">
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder="Suche…"
            className="w-full rounded border px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {isFetching && !isLoading ? (
            <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            </div>
          ) : null}
        </div>
        <label className="text-sm text-gray-600">
          <span className="sr-only">Nach Leistungstyp filtern</span>
          <select
            value={serviceTypeFilter}
            onChange={(e) => {
              setServiceTypeFilter(e.target.value as ServiceType | '')
              setPage(1)
            }}
            aria-label="Leistungstyp filtern"
            className="rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Alle Leistungstypen</option>
            <option value="customer">Kunde</option>
            <option value="supplier">Lieferant</option>
            <option value="employee">Mitarbeiter</option>
            <option value="shareholder">Gesellschafter</option>
            <option value="authority">Behörde</option>
            <option value="internal_transfer">Interne Umbuchung</option>
            <option value="unknown">Unbekannt</option>
          </select>
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600 select-none">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => {
              setShowInactive(e.target.checked)
              setPage(1)
            }}
            className="h-4 w-4 rounded border-gray-300"
          />
          <span>Inaktive anzeigen</span>
        </label>
        {showInactive && !isReadOnly && (
          <button
            onClick={() => {
              const inactive = (data?.items ?? []).filter((p) => !p.is_active)
              setSelectedPartners((prev) => {
                const next = new Map(prev)
                inactive.forEach((p) => next.set(p.id, p))
                return next
              })
            }}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            Alle inaktiven auswählen
          </button>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="w-10 px-3 py-3">
                <input
                  type="checkbox"
                  aria-label="Alle auf dieser Seite auswählen"
                  checked={allOnPageSelected}
                  ref={(el) => { if (el) el.indeterminate = someOnPageSelected && !allOnPageSelected }}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 cursor-pointer rounded border-gray-300"
                />
              </th>
              <SortableHeader label="Name" align="left" active={sortBy === 'name'} direction={sortDir} onClick={() => toggleSort('name')} />
              <th className="px-4 py-3 text-left">Leistungen</th>
              <SortableHeader label="IBANs" align="right" active={sortBy === 'iban_count'} direction={sortDir} onClick={() => toggleSort('iban_count')} />
              <SortableHeader label="Namen" align="right" active={sortBy === 'name_count'} direction={sortDir} onClick={() => toggleSort('name_count')} />
              <SortableHeader label="Buchungen" align="right" active={sortBy === 'journal_line_count'} direction={sortDir} onClick={() => toggleSort('journal_line_count')} />
              <SortableHeader label="Status" align="left" active={sortBy === 'status'} direction={sortDir} onClick={() => toggleSort('status')} />
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(data?.items.length ?? 0) === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-gray-400">
                  Keine Partner gefunden.
                </td>
              </tr>
            )}
            {(data?.items ?? []).map((p) => (
              <tr
                key={p.id}
                className={`hover:bg-gray-50 ${selectedPartners.has(p.id) ? 'bg-blue-50' : ''}`}
              >
                <td className="px-3 py-3">
                  <input
                    type="checkbox"
                    aria-label={`${p.display_name ?? p.name} auswählen`}
                    checked={selectedPartners.has(p.id)}
                    onChange={() => toggleSelect(p)}
                    className="h-4 w-4 cursor-pointer rounded border-gray-300"
                  />
                </td>
                <td className="px-4 py-3 font-medium text-gray-900">
                  {p.display_name ?? p.name}
                  {p.display_name && (
                    <span className="ml-2 text-xs text-gray-400">({p.name})</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {[...new Set(p.service_types)].map((serviceType) => {
                      const badge = serviceTypeBadges[serviceType]
                      return (
                        <span
                          key={serviceType}
                          aria-label={`Leistungstyp ${badge.label}`}
                          title={badge.label}
                          className={`inline-flex h-7 min-w-7 items-center justify-center rounded-full px-2 text-xs font-semibold ${badge.className}`}
                        >
                          {badge.short}
                        </span>
                      )
                    })}
                    {p.service_types.length === 0 ? (
                      <span className="text-xs text-gray-400">-</span>
                    ) : null}
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-gray-500">{p.iban_count}</td>
                <td className="px-4 py-3 text-right text-gray-500">{p.name_count}</td>
                <td className="px-4 py-3 text-right font-medium text-gray-700">{p.journal_line_count}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      p.is_active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-400 line-through'
                    }`}
                  >
                    {p.is_active ? 'Aktiv' : 'Inaktiv'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    to={`/partners/${p.id}`}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    Details
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="mt-4 flex justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
          >
            ← Zurück
          </button>
          <span className="px-3 py-1 text-sm text-gray-500">
            {page} / {data.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="rounded px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
          >
            Weiter →
          </button>
        </div>
      )}

      {showBulkMerge && (
        <BulkMergeDialog
          sources={[...selectedPartners.values()]}
          onClose={() => setShowBulkMerge(false)}
          onSuccess={() => {
            setShowBulkMerge(false)
            setSelectedPartners(new Map())
          }}
        />
      )}
    </div>
  )
}

function SortableHeader({
  label,
  align,
  active,
  direction,
  onClick,
}: {
  label: string
  align: 'left' | 'right'
  active: boolean
  direction: SortDirection
  onClick: () => void
}) {
  return (
    <th className={`px-4 py-3 ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 hover:text-gray-700 ${align === 'right' ? 'justify-end' : ''}`}
        aria-label={`${label} sortieren`}
      >
        <span>{label}</span>
        <span aria-hidden="true" className={active ? 'text-gray-700' : 'text-gray-300'}>
          {active ? (direction === 'asc' ? '↑' : '↓') : '↕'}
        </span>
      </button>
    </th>
  )
}
