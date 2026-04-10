import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { createUser, updateUser } from '@/api/users'
import type { UserListItem } from '@/api/users'

const createSchema = z.object({
  email: z.email('Ungültige E-Mail-Adresse'),
  role: z.enum(['viewer', 'accountant', 'mandant_admin', 'admin']),
})

const editSchema = z.object({
  email: z.email('Ungültige E-Mail-Adresse'),
  role: z.enum(['viewer', 'accountant', 'mandant_admin', 'admin']),
})

type CreateValues = z.infer<typeof createSchema>
type EditValues = z.infer<typeof editSchema>

interface UserDialogProps {
  onClose: () => void
  user?: UserListItem
}

export function UserDialog({ onClose, user }: UserDialogProps) {
  const queryClient = useQueryClient()
  const isEdit = user != null

  const createMutation = useMutation({
    mutationFn: (data: CreateValues) => createUser(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })

  const editMutation = useMutation({
    mutationFn: (data: EditValues) => updateUser(user!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
  })

  const editForm = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: { email: user?.email ?? '', role: (user?.role as EditValues['role']) ?? 'viewer' },
  })

  if (isEdit) {
    const { register, handleSubmit, formState: { errors, isSubmitting } } = editForm
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
        <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
          <h2 className="mb-4 text-lg font-semibold">Benutzer bearbeiten</h2>
          <form onSubmit={handleSubmit((v) => editMutation.mutate(v))} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">E-Mail</label>
              <input
                {...register('email')}
                type="email"
                className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {errors.email && <p className="mt-1 text-xs text-red-500">{errors.email.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Rolle</label>
              <select
                {...register('role')}
                className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="viewer">Viewer</option>
                <option value="accountant">Accountant</option>
                <option value="mandant_admin">Mandant-Admin</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            {editMutation.isError && (
              <p className="text-sm text-red-500">Fehler beim Speichern.</p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
              >
                Abbrechen
              </button>
              <button
                type="submit"
                disabled={isSubmitting || editMutation.isPending}
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Speichern
              </button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  const { register, handleSubmit, formState: { errors, isSubmitting } } = createForm
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Neuer Benutzer</h2>
        <form onSubmit={handleSubmit((v) => createMutation.mutate(v))} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">E-Mail</label>
            <input
              {...register('email')}
              type="email"
              className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.email && <p className="mt-1 text-xs text-red-500">{errors.email.message}</p>}
          </div>
          <p className="text-xs text-gray-500">
            Der Benutzer erhält eine Einladungs-E-Mail zum Setzen des Passworts.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700">Rolle</label>
            <select
              {...register('role')}
              className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="viewer">Viewer</option>
              <option value="accountant">Accountant</option>
              <option value="mandant_admin">Mandant-Admin</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {createMutation.isError && (
            <p className="text-sm text-red-500">Fehler beim Anlegen des Benutzers.</p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={isSubmitting || createMutation.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

