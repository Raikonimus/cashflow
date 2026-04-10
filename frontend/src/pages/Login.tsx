import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate, Link } from 'react-router-dom'
import { z } from 'zod'
import { loginUser } from '@/api/auth'
import { useAuthStore } from '@/store/auth-store'

const schema = z.object({
  email: z.string().email('Ungültige E-Mail-Adresse'),
  password: z.string().min(1, 'Passwort ist erforderlich'),
})

type FormValues = z.infer<typeof schema>

export function Login() {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const [error, setError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    setError(null)
    try {
      const data = await loginUser(values.email, values.password)
      login(data.access_token, data.mandants)
      if (data.requires_mandant_selection) {
        navigate('/login/select-mandant')
      } else {
        navigate('/')
      }
    } catch {
      setError('E-Mail oder Passwort ungültig.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">CashFlow</h1>
          <p className="mt-1 text-sm text-gray-500">Melde dich mit deinem Konto an</p>
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
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              E-Mail
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              {...register('email')}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {errors.email && (
              <p className="text-xs text-red-600 dark:text-red-400">{errors.email.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Passwort
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register('password')}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {errors.password && (
              <p className="text-xs text-red-600 dark:text-red-400">{errors.password.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors"
          >
            {isSubmitting ? 'Anmelden…' : 'Anmelden'}
          </button>

          <div className="text-center">
            <Link
              to="/forgot-password"
              className="text-xs text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
            >
              Passwort vergessen?
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
