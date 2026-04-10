import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { resetPassword } from '@/api/auth'

const schema = z
  .object({
    password: z.string().min(8, 'Passwort muss mindestens 8 Zeichen haben'),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: 'Passwörter stimmen nicht überein',
    path: ['confirm'],
  })

type FormValues = z.infer<typeof schema>

export function ResetPassword() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [error, setError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
        <div className="w-full max-w-md text-center space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Ungültiger oder fehlender Reset-Link.
          </p>
          <Link
            to="/forgot-password"
            className="text-sm text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
          >
            Neuen Reset-Link anfordern
          </Link>
        </div>
      </div>
    )
  }

  async function onSubmit(values: FormValues) {
    setError(null)
    try {
      await resetPassword(token!, values.password)
      navigate('/login', { state: { message: 'Passwort erfolgreich geändert.' } })
    } catch {
      setError('Der Reset-Link ist ungültig oder abgelaufen.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Neues Passwort</h1>
          <p className="mt-1 text-sm text-gray-500">Wähle ein sicheres neues Passwort</p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-sm space-y-4"
        >
          {error && (
            <div
              role="alert"
              className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400"
            >
              {error}
            </div>
          )}

          <div className="space-y-1">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Neues Passwort
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              {...register('password')}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {errors.password && (
              <p className="text-xs text-red-600 dark:text-red-400">{errors.password.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="confirm"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Passwort bestätigen
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              {...register('confirm')}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {errors.confirm && (
              <p className="text-xs text-red-600 dark:text-red-400">{errors.confirm.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors"
          >
            {isSubmitting ? 'Speichern…' : 'Passwort speichern'}
          </button>
        </form>
      </div>
    </div>
  )
}
