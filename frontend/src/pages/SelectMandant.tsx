import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { selectMandant } from '@/api/auth'
import { useAuthStore, type MandantInfo } from '@/store/auth-store'

/**
 * Die Mandantenauswahl nach dem Anmelden — und die Erklärung, wenn es nichts zu
 * wählen gibt.
 *
 * Drei Zustände, die sich alle aus dem Store ergeben:
 *
 * 1. **Mehrere Mandanten** → die Liste zur Auswahl. Ein Klick holt über
 *    `/auth/select-mandant` ein Token mit `mandant_id`.
 * 2. **Kein Mandant** → ein benannter Hinweis. Früher schickte diese Seite den
 *    Nutzer in diesem Fall zurück nach `/login`, wo die Anmeldemaske stand, obwohl
 *    ein gültiges Token im Store lag — eine Schleife ohne Erklärung (Befund M6).
 *    Das trifft jeden neu eingeladenen Nutzer, denn das Anlegen erzeugt für sich
 *    noch keine Zuordnung.
 * 3. **Kein Token** → zurück zur Anmeldung, hier ist niemand angemeldet.
 *
 * Der Fall „genau ein Mandant" kommt hier nicht mehr an: Der Server legt ihn beim
 * Anmelden direkt ins Token. Diese Seite wählte ihn früher zusätzlich selbst aus,
 * ebenso wie `Login.tsx` — zwei Stellen für dieselbe Entscheidung (Befund M2).
 */
export function SelectMandant() {
  const navigate = useNavigate()
  const { mandants, selectMandant: storeSelectMandant, token, logout } = useAuthStore()
  const [fehler, setFehler] = useState<string | null>(null)

  const handleSelect = useCallback(
    async (mandant: MandantInfo) => {
      setFehler(null)
      try {
        const data = await selectMandant(mandant.id)
        storeSelectMandant(mandant, data.access_token)
        navigate('/', { replace: true })
      } catch {
        // Der Mandant kann inzwischen deaktiviert oder die Zuordnung entzogen worden
        // sein. Auf der Seite bleiben und es sagen — die übrigen Einträge können
        // weiterhin funktionieren.
        setFehler(`„${mandant.name}" ist derzeit nicht verfügbar.`)
      }
    },
    [navigate, storeSelectMandant],
  )

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  if (!token) {
    return <MeldungsRahmen titel="Nicht angemeldet" text="Bitte melde dich neu an." />
  }

  if (mandants.length === 0) {
    return (
      <MeldungsRahmen
        titel="Kein Mandant zugeordnet"
        text={
          'Dein Konto ist noch keinem Mandanten zugeordnet. Bis das geschehen ist, ' +
          'gibt es keine Daten, die angezeigt werden könnten. Wende dich an die ' +
          'Benutzerverwaltung.'
        }
      >
        <button
          onClick={handleLogout}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          Abmelden
        </button>
      </MeldungsRahmen>
    )
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

        {fehler && (
          <div
            role="alert"
            className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400"
          >
            {fehler}
          </div>
        )}

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

/** Rahmen für die Fälle, in denen es nichts zu wählen gibt, sondern etwas zu sagen. */
function MeldungsRahmen({
  titel,
  text,
  children,
}: Readonly<{
  titel: string
  text: string
  children?: React.ReactNode
}>) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-4 text-center">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">{titel}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>
        {children}
      </div>
    </div>
  )
}
