import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { selectMandant } from '@/api/auth'
import { useAuthStore, type MandantInfo } from '@/store/auth-store'

/**
 * Zeigt den aktiven Mandanten und lässt zwischen den zugeordneten wechseln.
 *
 * Vorher stand der Mandantenname nur als Text im Kopfbereich; wechseln ging allein
 * über Abmelden und neu Anmelden. Sobald eine E-Mail-Adresse zu mehreren Mandanten
 * gehört — seit dem 10.09.2026 der Regelfall statt der Ausnahme — ist das der Weg,
 * den man mehrmals am Tag geht (Entscheidung E4).
 *
 * Bei genau einem Mandanten bleibt es bei der reinen Anzeige: Ein Menü mit einem
 * Eintrag, der schon aktiv ist, wäre eine Schaltfläche, die nichts tut.
 *
 * **Warum der Cache geleert wird:** Jede geladene Tabelle, Auswertung und Liste
 * gehört zu genau einem Mandanten. Die meisten Abfragen tragen die `mandant_id` im
 * Schlüssel und würden von sich aus neu laden — aber „die meisten" genügt hier
 * nicht: Eine einzige Abfrage ohne `mandant_id` im Schlüssel würde nach dem Wechsel
 * die Zahlen des vorherigen Mandanten weiter anzeigen, und niemand würde es merken.
 * Deshalb wird der gesamte Cache verworfen, nicht selektiv entwertet.
 */
export function MandantSwitcher() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { mandants, selectedMandant, selectMandant: storeSelectMandant } = useAuthStore()
  const [offen, setOffen] = useState(false)
  const [wechselt, setWechselt] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)

  const beschriftung = selectedMandant?.name ?? 'Kein Mandant'

  async function handleWechsel(mandant: MandantInfo) {
    if (mandant.id === selectedMandant?.id) {
      setOffen(false)
      return
    }
    setWechselt(mandant.id)
    setFehler(null)
    try {
      const daten = await selectMandant(mandant.id)
      storeSelectMandant(mandant, daten.access_token)
      queryClient.clear()
      setOffen(false)
      navigate('/', { replace: true })
    } catch {
      setFehler(`Wechsel zu „${mandant.name}" nicht möglich.`)
    } finally {
      setWechselt(null)
    }
  }

  if (mandants.length <= 1) {
    return selectedMandant ? (
      <span className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
        {selectedMandant.name}
      </span>
    ) : null
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOffen((aktuell) => !aktuell)}
        aria-haspopup="menu"
        aria-expanded={offen}
        aria-label={`Mandant wechseln — aktuell ${beschriftung}`}
        className="inline-flex items-center gap-1 rounded bg-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-600 transition-colors"
      >
        {beschriftung}
        <span aria-hidden="true" className="text-[0.6rem]">
          ▾
        </span>
      </button>

      {offen && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-2 min-w-56 overflow-hidden rounded-xl border border-gray-700 bg-gray-800 shadow-lg"
        >
          <div className="border-b border-gray-700 px-4 py-2 text-[0.7rem] uppercase tracking-wide text-gray-400">
            Mandant wechseln
          </div>
          <div className="py-1">
            {mandants.map((m) => {
              const aktiv = m.id === selectedMandant?.id
              return (
                <button
                  key={m.id}
                  type="button"
                  role="menuitem"
                  onClick={() => handleWechsel(m)}
                  disabled={wechselt !== null}
                  className={`block w-full px-4 py-2 text-left text-sm transition-colors disabled:opacity-50 ${
                    aktiv
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-200 hover:bg-gray-700 hover:text-white'
                  }`}
                >
                  {m.name}
                  {aktiv && <span className="ml-2 text-xs text-gray-400">aktiv</span>}
                  {wechselt === m.id && (
                    <span className="ml-2 text-xs text-gray-400">wechselt…</span>
                  )}
                </button>
              )
            })}
          </div>
          {fehler && (
            <p role="alert" className="border-t border-gray-700 px-4 py-2 text-xs text-red-400">
              {fehler}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
