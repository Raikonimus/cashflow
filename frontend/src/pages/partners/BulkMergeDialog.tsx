import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { listPartners, mergePartners } from '@/api/partners'
import type { PartnerListItem } from '@/api/partners'

interface Source {
  id: string
  name: string
  display_name: string | null
}

interface BulkMergeDialogProps {
  sources: Source[]
  onClose: () => void
  onSuccess: () => void
}

export function BulkMergeDialog({ sources, onClose, onSuccess }: BulkMergeDialogProps) {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PartnerListItem[]>([])
  const [target, setTarget] = useState<PartnerListItem | null>(null)
  const [searching, setSearching] = useState(false)
  const queryClient = useQueryClient()

  const sourceIds = new Set(sources.map((s) => s.id))

  const mutation = useMutation({
    mutationFn: async () => {
      if (!target) throw new Error('Kein Ziel-Partner ausgewählt')
      const toMerge = sources.filter((s) => s.id !== target.id)
      for (const source of toMerge) {
        await mergePartners(mandantId, source.id, target.id)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
      onSuccess()
    },
  })

  async function handleSearch(q: string) {
    setQuery(q)
    setTarget(null)
    if (q.length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    try {
      const data = await listPartners(mandantId, 1, 20, false, q)
      setResults(data.items.filter((p) => p.is_active))
    } finally {
      setSearching(false)
    }
  }

  const effectiveSources = target ? sources.filter((s) => s.id !== target.id) : sources

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-semibold">Partner zusammenführen</h2>
        <p className="mb-3 text-sm text-gray-500">
          Alle ausgewählten Partner werden in den Ziel-Partner gemergt und deaktiviert.
        </p>

        <div className="mb-4 max-h-36 overflow-y-auto rounded border border-gray-100 bg-gray-50 px-3 py-2">
          {sources.map((s) => (
            <div
              key={s.id}
              className={`py-0.5 text-sm ${target?.id === s.id ? 'font-semibold text-green-700' : 'text-gray-700'}`}
            >
              {target?.id === s.id ? '✓ ' : '→ '}
              {s.display_name ?? s.name}
              {target?.id === s.id && (
                <span className="ml-1 text-xs text-green-600">(Ziel)</span>
              )}
            </div>
          ))}
        </div>

        <label className="block text-sm font-medium text-gray-700">Ziel-Partner suchen</label>
        <input
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Name eingeben…"
          autoFocus
          className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        {searching && <p className="mt-1 text-xs text-gray-400">Suche…</p>}

        {results.length > 0 && !target && (
          <ul className="mt-1 max-h-40 divide-y divide-gray-100 overflow-y-auto rounded border border-gray-200 bg-white shadow-sm">
            {results.map((p) => (
              <li
                key={p.id}
                onClick={() => {
                  setTarget(p)
                  setQuery(p.display_name ?? p.name)
                  setResults([])
                }}
                className="cursor-pointer px-3 py-2 text-sm hover:bg-blue-50"
              >
                {p.display_name ?? p.name}
                {p.display_name && (
                  <span className="ml-2 text-xs text-gray-400">({p.name})</span>
                )}
                {sourceIds.has(p.id) && (
                  <span className="ml-2 rounded bg-green-100 px-1 text-xs text-green-700">
                    aus Auswahl
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}

        {target && effectiveSources.length > 0 && (
          <div className="mt-3 rounded bg-orange-50 px-3 py-2 text-sm text-orange-800">
            ⚠ <strong>{effectiveSources.length}</strong> Partner{effectiveSources.length > 1 ? ' werden' : ' wird'} in{' '}
            <strong>{target.display_name ?? target.name}</strong> gemergt und deaktiviert.
            Diese Aktion kann nicht rückgängig gemacht werden.
          </div>
        )}

        {target && effectiveSources.length === 0 && (
          <div className="mt-3 rounded bg-gray-100 px-3 py-2 text-sm text-gray-600">
            Der gewählte Ziel-Partner ist der einzige in der Auswahl – nichts zu tun.
          </div>
        )}

        {mutation.isError && (
          <p className="mt-2 text-sm text-red-500">
            {mutation.error instanceof Error ? mutation.error.message : 'Fehler beim Mergen.'}
          </p>
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
            disabled={!target || effectiveSources.length === 0 || mutation.isPending}
            className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
          >
            {mutation.isPending ? 'Wird zusammengeführt…' : 'Zusammenführen'}
          </button>
        </div>
      </div>
    </div>
  )
}
