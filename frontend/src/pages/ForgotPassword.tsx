import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { forgotPassword } from '@/api/auth'

const schema = z.object({
  email: z.string().email('Ungültige E-Mail-Adresse'),
})

type FormValues = z.infer<typeof schema>

export function ForgotPassword() {
  const [submitted, setSubmitted] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    // Always show success toast regardless of whether email exists (anti-enumeration)
    await forgotPassword(values.email).catch(() => {
      /* swallow — always 200 */
    })
    setSubmitted(true)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            Passwort vergessen
          </h1>
          <p className="mt-1 text-sm text-gray-500">Wir senden dir einen Reset-Link per E-Mail</p>
        </div>

        <div className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-sm space-y-4">
          {submitted ? (
            <div
              role="status"
              className="rounded-md bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 px-4 py-3 text-sm text-green-700 dark:text-green-400"
            >
              Falls diese E-Mail-Adresse registriert ist, wurde eine E-Mail gesendet.
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
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

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors"
              >
                {isSubmitting ? 'Senden…' : 'Reset-Link senden'}
              </button>
            </form>
          )}

          <div className="text-center">
            <Link
              to="/login"
              className="text-xs text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
            >
              ← Zurück zum Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
