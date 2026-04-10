import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listUsers, updateUser, deleteUser } from '@/api/users'
import type { UserListItem } from '@/api/users'
import { UserDialog } from './UserDialog'

const INV_LABELS: Record<string, string> = {
  pending: 'Einladung ausstehend',
  accepted: 'Aktiv',
  expired: 'Einladung abgelaufen',
}

const ROLE_LABELS: Record<string, string> = {
  viewer: 'Viewer',
  accountant: 'Accountant',
  mandant_admin: 'Mandant-Admin',
  admin: 'Admin',
}

export function UsersPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [editingUser, setEditingUser] = useState<UserListItem | null>(null)
  const queryClient = useQueryClient()

  const { data: users = [], isLoading, isError } = useQuery({
    queryKey: ['users'],
    queryFn: listUsers,
  })

  const toggleActive = useMutation({
    mutationFn: (user: UserListItem) =>
      updateUser(user.id, { is_active: !user.is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  function handleDelete(user: UserListItem) {
    if (!window.confirm(`Benutzer "${user.email}" wirklich löschen?`)) return
    deleteMutation.mutate(user.id)
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
        Fehler beim Laden der Benutzer.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Benutzerverwaltung</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Neuer Benutzer
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">E-Mail</th>
              <th className="px-4 py-3 text-left">Rolle</th>
              <th className="px-4 py-3 text-left">Einladung</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Erstellt</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-gray-400">
                  Keine Benutzer vorhanden.
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{u.email}</td>
                <td className="px-4 py-3 text-gray-600">
                  {ROLE_LABELS[u.role] ?? u.role}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {INV_LABELS[u.invitation_status] ?? u.invitation_status}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => toggleActive.mutate(u)}
                    disabled={toggleActive.isPending}
                    className={`rounded px-2 py-1 text-xs font-medium ${
                      u.is_active
                        ? 'bg-green-100 text-green-700 hover:bg-green-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    {u.is_active ? 'Aktiv' : 'Inaktiv'}
                  </button>
                </td>
                <td className="px-4 py-3 text-gray-400">
                  {u.created_at ? new Date(u.created_at + 'Z').toLocaleDateString('de-DE', { timeZone: 'Europe/Vienna' }) : '–'}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setEditingUser(u)}
                      className="rounded px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50"
                    >
                      Bearbeiten
                    </button>
                    <button
                      onClick={() => handleDelete(u)}
                      disabled={deleteMutation.isPending}
                      className="rounded px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      Löschen
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && <UserDialog onClose={() => setShowCreate(false)} />}
      {editingUser && (
        <UserDialog user={editingUser} onClose={() => setEditingUser(null)} />
      )}
    </div>
  )
}
