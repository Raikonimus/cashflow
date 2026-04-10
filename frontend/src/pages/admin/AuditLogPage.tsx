import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { listAuditLog } from '@/api/journal'
import type { AuditLogEntry } from '@/api/journal'

export function AuditLogPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const { data, isLoading, isError } = useQuery({
    queryKey: ['audit', mandantId, page],
    queryFn: () => listAuditLog(mandantId, page, 25),
    enabled: !!mandantId,
  })

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

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
        Fehler beim Laden des Audit-Logs.
      </div>
    )
  }

  const entries = data?.items ?? []

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Audit-Log</h1>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">Datum</th>
              <th className="px-4 py-3 text-left">Aktion</th>
              <th className="px-4 py-3 text-left">Akteur</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-400">
                  Keine Einträge vorhanden.
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <AuditRow
                key={entry.id}
                entry={entry}
                expanded={expanded.has(entry.id)}
                onToggle={() => toggleExpand(entry.id)}
              />
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

// ─── Audit Row ────────────────────────────────────────────────────────────────

function AuditRow({
  entry,
  expanded,
  onToggle,
}: {
  entry: AuditLogEntry
  expanded: boolean
  onToggle: () => void
}) {
  const eventColor: Record<string, string> = {
    'partner.merged': 'bg-purple-100 text-purple-700',
    'journal.bulk_assign': 'bg-blue-100 text-blue-700',
    'review.confirmed': 'bg-green-100 text-green-700',
    'review.reassigned': 'bg-orange-100 text-orange-700',
    'review.new_partner': 'bg-yellow-100 text-yellow-700',
    'auth.login': 'bg-green-100 text-green-700',
    'auth.logout': 'bg-gray-100 text-gray-500',
    'import.completed': 'bg-blue-100 text-blue-700',
    'import.failed': 'bg-red-100 text-red-700',
  }
  const colorCls = eventColor[entry.event_type] ?? 'bg-gray-100 text-gray-600'

  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-4 py-3 font-mono text-xs text-gray-500">
          {new Date(entry.created_at + 'Z').toLocaleString('de-DE', { timeZone: 'Europe/Vienna' })}
        </td>
        <td className="px-4 py-3">
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${colorCls}`}>
            {entry.event_type}
          </span>
        </td>
        <td className="px-4 py-3 font-mono text-xs text-gray-500">
          {entry.actor_id.substring(0, 8)}…
        </td>
        <td className="px-4 py-3 text-right">
          <button
            onClick={onToggle}
            className="text-xs text-blue-500 hover:underline"
          >
            {expanded ? 'Ausblenden' : 'Details'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={4} className="px-4 py-3">
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-gray-100 p-3 font-mono text-xs text-gray-700">
              {JSON.stringify(entry.payload, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}
