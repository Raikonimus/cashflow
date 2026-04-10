import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { listMandants, createMandant } from '@/api/users'
import { selectMandant } from '@/api/auth'
import { useAuthStore } from '@/store/auth-store'

const schema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(255),
})
type FormValues = z.infer<typeof schema>

export function MandantsPage() {
  const [showForm, setShowForm] = useState(false)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { selectMandant: storeSelect } = useAuthStore()

  const { data: mandants = [], isLoading, isError } = useQuery({
    queryKey: ['mandants'],
    queryFn: listMandants,
  })

  const mutation = useMutation({
    mutationFn: (data: FormValues) => createMandant(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mandants'] })
      setShowForm(false)
      reset()
    },
  })

  const enterMandant = useMutation({
    mutationFn: (id: string) => selectMandant(id),
    onSuccess: (data, id) => {
      const mandant = mandants.find((m) => m.id === id)
      if (mandant) storeSelect({ id: mandant.id, name: mandant.name }, data.access_token)
      navigate('/')
    },
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

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
        Fehler beim Laden der Mandanten.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Mandanten</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {showForm ? 'Abbrechen' : '+ Neuer Mandant'}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleSubmit((v) => mutation.mutate(v))}
          className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
        >
          <div className="flex gap-3">
            <div className="flex-1">
              <input
                {...register('name')}
                placeholder="Mandantenname"
                className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {errors.name && (
                <p className="mt-1 text-xs text-red-500">{errors.name.message}</p>
              )}
            </div>
            <button
              type="submit"
              disabled={isSubmitting || mutation.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
          {mutation.isError && (
            <p className="mt-2 text-sm text-red-500">Fehler beim Anlegen.</p>
          )}
        </form>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Erstellt</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {mandants.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-gray-400">
                  Keine Mandanten vorhanden.
                </td>
              </tr>
            )}
            {mandants.map((m) => (
              <tr key={m.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{m.name}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-1 text-xs font-medium ${
                      m.is_active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    {m.is_active ? 'Aktiv' : 'Inaktiv'}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400">
                  {new Date(m.created_at + 'Z').toLocaleDateString('de-DE', { timeZone: 'Europe/Vienna' })}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => enterMandant.mutate(m.id)}
                    disabled={enterMandant.isPending}
                    className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    Einsteigen
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
