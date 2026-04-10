import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuthStore } from '@/store/auth-store'
import { listPartners, createPartner } from '@/api/partners'

export function PartnersPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showForm, setShowForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['partners', mandantId, page, showInactive],
    queryFn: () => listPartners(mandantId, page, 30, showInactive),
    enabled: !!mandantId,
  })

  const createMutation = useMutation({
    mutationFn: () => createPartner(mandantId, newName.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      setNewName('')
      setShowForm(false)
    },
  })

  const filtered = (data?.items ?? []).filter((p) =>
    (p.display_name ?? p.name).toLowerCase().includes(search.toLowerCase()),
  )

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

      <div className="mb-4 flex items-center gap-4">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Suche…"
          className="flex-1 rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600 select-none">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => { setShowInactive(e.target.checked); setPage(1) }}
            className="h-4 w-4 rounded border-gray-300"
          />
          Inaktive anzeigen
        </label>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-right">IBANs</th>
              <th className="px-4 py-3 text-right">Namen</th>
              <th className="px-4 py-3 text-right">Muster</th>
              <th className="px-4 py-3 text-right">Buchungen</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-400">
                  Keine Partner gefunden.
                </td>
              </tr>
            )}
            {filtered.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">
                  {p.display_name ?? p.name}
                  {p.display_name && (
                    <span className="ml-2 text-xs text-gray-400">({p.name})</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-gray-500">{p.iban_count}</td>
                <td className="px-4 py-3 text-right text-gray-500">{p.name_count}</td>
                <td className="px-4 py-3 text-right text-gray-500">{p.pattern_count}</td>
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
    </div>
  )
}
