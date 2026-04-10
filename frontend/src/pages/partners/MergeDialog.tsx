import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { listPartners, mergePartners } from '@/api/partners'
import type { PartnerListItem } from '@/api/partners'

interface MergeDialogProps {
  sourcePartner: { id: string; name: string }
  onClose: () => void
  onSuccess: () => void
}

export function MergeDialog({ sourcePartner, onClose, onSuccess }: MergeDialogProps) {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PartnerListItem[]>([])
  const [selected, setSelected] = useState<PartnerListItem | null>(null)
  const [searching, setSearching] = useState(false)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => mergePartners(mandantId, sourcePartner.id, selected!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      queryClient.invalidateQueries({ queryKey: ['partner', mandantId, sourcePartner.id] })
      onSuccess()
    },
  })

  async function handleSearch(q: string) {
    setQuery(q)
    setSelected(null)
    if (q.length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    try {
      const data = await listPartners(mandantId, 1, 20, false, q)
      setResults(data.items.filter((p) => p.id !== sourcePartner.id && p.is_active))
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-semibold">Partner zusammenführen</h2>
        <p className="mb-4 text-sm text-gray-500">
          <strong>{sourcePartner.name}</strong> wird in den Ziel-Partner gemergt und deaktiviert.
          Alle Buchungszeilen, IBANs und Namensvarianten werden übertragen.
        </p>

        <label className="block text-sm font-medium text-gray-700">Ziel-Partner suchen</label>
        <input
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Name eingeben…"
          className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        {searching && <p className="mt-1 text-xs text-gray-400">Suche…</p>}

        {results.length > 0 && !selected && (
          <ul className="mt-1 divide-y divide-gray-100 rounded border border-gray-200 bg-white shadow-sm">
            {results.map((p) => (
              <li
                key={p.id}
                onClick={() => {
                  setSelected(p)
                  setQuery(p.display_name ?? p.name)
                  setResults([])
                }}
                className="cursor-pointer px-3 py-2 text-sm hover:bg-blue-50"
              >
                {p.display_name ?? p.name}
                {p.display_name && (
                  <span className="ml-2 text-xs text-gray-400">({p.name})</span>
                )}
              </li>
            ))}
          </ul>
        )}

        {selected && (
          <div className="mt-3 rounded bg-orange-50 px-3 py-2 text-sm text-orange-800">
            ⚠ <strong>{sourcePartner.name}</strong> wird in <strong>{selected.display_name ?? selected.name}</strong> gemergt.
            Diese Aktion kann nicht rückgängig gemacht werden.
          </div>
        )}

        {mutation.isError && (
          <p className="mt-2 text-sm text-red-500">Fehler beim Mergen. Bitte erneut versuchen.</p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            Abbrechen
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!selected || mutation.isPending}
            className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
          >
            {mutation.isPending ? 'Merging…' : 'Zusammenführen'}
          </button>
        </div>
      </div>
    </div>
  )
}
