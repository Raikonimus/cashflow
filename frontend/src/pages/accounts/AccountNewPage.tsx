import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuthStore } from '@/store/auth-store'
import { createAccount } from '@/api/accounts'

const schema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(255),
})
type FormValues = z.infer<typeof schema>

export function AccountNewPage() {
  const navigate = useNavigate()
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (data: FormValues) => createAccount(mandantId, data),
    onSuccess: (acc) => {
      queryClient.invalidateQueries({ queryKey: ['accounts', mandantId] })
      navigate(`/accounts/${acc.id}`)
    },
  })

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Neues Konto anlegen</h1>

      <form
        onSubmit={handleSubmit((v) => mutation.mutate(v))}
        className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <div>
          <label className="block text-sm font-medium text-gray-700">Kontoname</label>
          <input
            {...register('name')}
            className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="z. B. Girokonto Sparkasse"
          />
          {errors.name && (
            <p className="mt-1 text-xs text-red-500">{errors.name.message}</p>
          )}
        </div>

        {mutation.isError && (
          <p className="text-sm text-red-500">Fehler beim Anlegen des Kontos.</p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={() => navigate('/accounts')}
            className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            disabled={isSubmitting || mutation.isPending}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      </form>
    </div>
  )
}
