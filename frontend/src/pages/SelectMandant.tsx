import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { selectMandant } from '@/api/auth'
import { useAuthStore, type MandantInfo } from '@/store/auth-store'

export function SelectMandant() {
  const navigate = useNavigate()
  const { mandants, selectMandant: storeSelectMandant, token } = useAuthStore()

  useEffect(() => {
    if (!token || mandants.length === 0) {
      navigate('/login', { replace: true })
    }
  }, [mandants.length, navigate, token])

  useEffect(() => {
    if (!token || mandants.length !== 1) {
      return
    }

    void handleSelect(mandants[0])
  }, [mandants, token])

  if (!token || mandants.length === 0) {
    return null
  }

  // Single-mandant: auto-select is running in the effect above — show nothing
  if (mandants.length === 1) {
    return null
  }

  async function handleSelect(mandant: MandantInfo) {
    try {
      const data = await selectMandant(mandant.id)
      storeSelectMandant(mandant, data.access_token)
      navigate('/', { replace: true })
    } catch {
      // stay on page, user can retry
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            Mandant auswählen
          </h1>
          <p className="mt-1 text-sm text-gray-500">Wähle den Mandanten für diese Sitzung</p>
        </div>

        <div className="space-y-2">
          {mandants.map((m) => (
            <button
              key={m.id}
              onClick={() => handleSelect(m)}
              className="w-full rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 text-left text-sm font-medium text-gray-900 dark:text-white hover:bg-indigo-50 dark:hover:bg-indigo-900/20 hover:border-indigo-300 transition-colors"
            >
              {m.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
