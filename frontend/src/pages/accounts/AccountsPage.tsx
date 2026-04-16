import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuthStore } from '@/store/auth-store'
import { listAccounts } from '@/api/accounts'

export function AccountsPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')

  const { data: accounts = [], isLoading, isError } = useQuery({
    queryKey: ['accounts', mandantId],
    queryFn: () => listAccounts(mandantId),
    enabled: !!mandantId,
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
        Fehler beim Laden der Konten.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Konten</h1>
        <Link
          to="/accounts/new"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Neues Konto
        </Link>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {accounts.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-gray-400">
            Noch keine Konten vorhanden.{' '}
            <Link to="/accounts/new" className="text-blue-600 hover:underline">
              Jetzt anlegen
            </Link>
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {accounts.map((acc) => (
              <li key={acc.id} className="flex items-center justify-between px-4 py-3">
                <span className="font-medium text-gray-900">{acc.name}</span>
                <div className="flex gap-3">
                  <Link
                    to={`/accounts/${acc.id}`}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    Einstellungen
                  </Link>
                  <Link
                    to={`/accounts/${acc.id}/import`}
                    className="text-sm text-gray-600 hover:underline"
                  >
                    Import
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
