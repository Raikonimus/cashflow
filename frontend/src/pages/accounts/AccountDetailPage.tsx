import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { listAccounts } from '@/api/accounts'
import {
  listExcludedIdentifiers,
  addExcludedIdentifier,
  deleteExcludedIdentifier,
  applyExcludedIdentifiers,
} from '@/api/accounts'
import { MappingEditor } from './MappingEditor'

export function AccountDetailPage() {
  const { accountId } = useParams<{ accountId: string }>()
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts', mandantId],
    queryFn: () => listAccounts(mandantId),
    enabled: !!mandantId,
  })

  const account = accounts.find((a) => a.id === accountId)

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (!accountId || !account) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">
        Konto nicht gefunden.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-2 text-sm text-gray-400">
        <Link to="/accounts" className="hover:underline">
          Konten
        </Link>{' '}
        / {account.name}
      </div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{account.name}</h1>
        <Link
          to={`/accounts/${accountId}/import`}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          CSV importieren
        </Link>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-semibold text-gray-800">
          Spalten-Mapping
        </h2>
        <MappingEditor accountId={accountId} />
      </div>

      <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-1 text-base font-semibold text-gray-800">
          Ausgeschlossene Identifikatoren
        </h2>
        <p className="mb-4 text-sm text-gray-500">
          IBANs und Kontonummern, die in importierten Buchungen als Partnerdaten auftauchen, aber diesem Konto selbst gehören (z.&thinsp;B. bei Lastschriften). Diese werden bei der automatischen Partneridentifikation ignoriert.
        </p>
        <ExcludedIdentifiersSection mandantId={mandantId} accountId={accountId} />
      </div>
    </div>
  )
}

function ExcludedIdentifiersSection({
  mandantId,
  accountId,
}: {
  mandantId: string
  accountId: string
}) {
  const qc = useQueryClient()
  const [type, setType] = useState<'iban' | 'account_number'>('iban')
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [applyResult, setApplyResult] = useState<string | null>(null)

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['excluded-identifiers', accountId],
    queryFn: () => listExcludedIdentifiers(mandantId, accountId),
    enabled: !!mandantId && !!accountId,
  })

  const addMutation = useMutation({
    mutationFn: () =>
      addExcludedIdentifier(mandantId, accountId, {
        identifier_type: type,
        value: value.trim(),
        label: label.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['excluded-identifiers', accountId] })
      setValue('')
      setLabel('')
      setError(null)
      setApplyResult(null)
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? 'Fehler beim Speichern')
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => applyExcludedIdentifiers(mandantId, accountId),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['journal'] })
      setApplyResult(data.message)
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? 'Fehler bei der Datenbereinigung')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteExcludedIdentifier(mandantId, accountId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['excluded-identifiers', accountId] }),
  })

  function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    addMutation.mutate()
  }

  return (
    <div>
      <form onSubmit={handleAdd} className="mb-4 flex flex-wrap items-end gap-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">Typ</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as 'iban' | 'account_number')}
            className="rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="iban">IBAN</option>
            <option value="account_number">Kontonummer</option>
          </select>
        </div>
        <div className="flex-1 min-w-40">
          <label className="mb-1 block text-xs font-medium text-gray-600">Wert</label>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={type === 'iban' ? 'AT12 3456 …' : '49900997173'}
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            required
          />
        </div>
        <div className="flex-1 min-w-32">
          <label className="mb-1 block text-xs font-medium text-gray-600">Bezeichnung (optional)</label>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="z. B. Interne Bankgebühren"
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
        <button
          type="submit"
          disabled={addMutation.isPending || !value.trim()}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Hinzufügen
        </button>
      </form>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      {isLoading ? (
        <p className="text-sm text-gray-400">Laden …</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-gray-400">Keine ausgeschlossenen Identifikatoren definiert.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
              <th className="py-1.5 pr-4">Typ</th>
              <th className="py-1.5 pr-4">Wert</th>
              <th className="py-1.5 pr-4">Bezeichnung</th>
              <th className="py-1.5" />
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="border-b border-gray-50">
                <td className="py-1.5 pr-4 text-xs text-gray-500">
                  {e.identifier_type === 'iban' ? 'IBAN' : 'Kontonummer'}
                </td>
                <td className="py-1.5 pr-4 font-mono text-xs">{e.value}</td>
                <td className="py-1.5 pr-4 text-gray-600">{e.label ?? <span className="text-gray-300">—</span>}</td>
                <td className="py-1.5 text-right">
                  <button
                    onClick={() => deleteMutation.mutate(e.id)}
                    disabled={deleteMutation.isPending}
                    className="text-xs text-red-500 hover:underline disabled:opacity-40"
                  >
                    Entfernen
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {entries.length > 0 && (
        <div className="mt-4 flex items-center gap-3 border-t border-gray-100 pt-4">
          <button
            onClick={() => { setApplyResult(null); applyMutation.mutate() }}
            disabled={applyMutation.isPending}
            className="rounded bg-amber-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {applyMutation.isPending ? 'Wird geprüft …' : 'Datenbereinigung starten'}
          </button>
          {applyResult && (
            <span className="text-sm text-green-700">{applyResult}</span>
          )}
        </div>
      )}
    </div>
  )
}
