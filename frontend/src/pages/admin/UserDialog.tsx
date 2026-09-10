import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { createUser, listAssignableMandants, updateUser } from '@/api/users'
import type { UserListItem } from '@/api/users'
import { extractErrorMessage } from '@/api/errors'

const schema = z.object({
  email: z.email('Ungültige E-Mail-Adresse'),
  role: z.enum(['viewer', 'accountant', 'mandant_admin', 'admin']),
})

type FormValues = z.infer<typeof schema>

/** Was an den Server geht — das Formular plus die Mandantenauswahl. */
type Nutzlast = FormValues & { mandant_ids: string[] }

interface UserDialogProps {
  onClose: () => void
  user?: UserListItem
}

/**
 * Anlegen und Bearbeiten eines Benutzers — samt Mandantenzuordnung.
 *
 * **Ein Formular für beide Fälle.** Vorher hatte diese Datei zwei fast identische
 * Zweige mit je eigenem Formular; die Mandantenauswahl hätte in beide eingebaut
 * werden müssen, und der nächste Zusatz wieder. Genau daraus entstehen die stillen
 * Widersprüche zwischen zwei Stellen, die dasselbe tun sollen. Die Unterschiede
 * zwischen Anlegen und Bearbeiten sind jetzt Daten, nicht Struktur: Titel,
 * Schaltflächenbeschriftung, Vorbelegung und die Zielfunktion.
 *
 * **Zur Mandantenzuordnung:** Die Auswahl kommt aus `/users/assignable-mandants` und
 * enthält nur Mandanten, die der Anmeldende auch zuordnen *darf* — bei einem
 * Mandant-Admin also seine eigenen. Der Server gleicht beim Speichern ausschließlich
 * innerhalb dieser Menge ab; Zuordnungen des Nutzers zu anderen Mandanten bleiben
 * unberührt, obwohl sie in diesem Formular nicht auftauchen. Der Hinweis unten sagt
 * das, damit niemand annimmt, er sähe hier den vollständigen Stand.
 */
export function UserDialog({ onClose, user }: Readonly<UserDialogProps>) {
  const queryClient = useQueryClient()
  const istBearbeiten = user != null

  const { data: zuordenbare = [], isLoading: mandantenLaden } = useQuery({
    queryKey: ['assignable-mandants'],
    queryFn: listAssignableMandants,
  })

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: user?.email ?? '',
      role: (user?.role as FormValues['role']) ?? 'viewer',
    },
  })

  // Die Mandantenauswahl liegt bewusst in lokalem Zustand und nicht im Formular:
  // Sie braucht keine Validierung, und `watch()` aus react-hook-form lässt sich
  // nicht memoisieren — der React-Compiler würde die ganze Komponente überspringen.
  const [gewaehlt, setGewaehlt] = useState<string[]>(() => user?.mandants.map((m) => m.id) ?? [])

  const mutation = useMutation({
    mutationFn: (werte: Nutzlast) =>
      istBearbeiten ? updateUser(user.id, werte) : createUser(werte),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })

  function umschalten(mandantId: string) {
    setGewaehlt((aktuell) =>
      aktuell.includes(mandantId)
        ? aktuell.filter((id) => id !== mandantId)
        : [...aktuell, mandantId],
    )
  }

  // Zuordnungen zu Mandanten, die in dieser Auswahl nicht vorkommen. Sie bleiben beim
  // Speichern erhalten — das muss sichtbar sein, sonst wirkt die Liste unvollständig
  // oder falsch.
  const nichtSichtbare = (user?.mandants ?? []).filter(
    (m) => !zuordenbare.some((z) => z.id === m.id),
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">
          {istBearbeiten ? 'Benutzer bearbeiten' : 'Neuer Benutzer'}
        </h2>

        <form
          onSubmit={handleSubmit((v) => mutation.mutate({ ...v, mandant_ids: gewaehlt }))}
          className="space-y-4"
        >
          <div>
            <label htmlFor="user-email" className="block text-sm font-medium text-gray-700">
              E-Mail
            </label>
            <input
              id="user-email"
              {...register('email')}
              type="email"
              className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.email && <p className="mt-1 text-xs text-red-500">{errors.email.message}</p>}
          </div>

          <div>
            <label htmlFor="user-role" className="block text-sm font-medium text-gray-700">
              Rolle
            </label>
            <select
              id="user-role"
              {...register('role')}
              className="mt-1 w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="viewer">Viewer</option>
              <option value="accountant">Accountant</option>
              <option value="mandant_admin">Mandant-Admin</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <fieldset>
            <legend className="block text-sm font-medium text-gray-700">Mandanten</legend>

            {mandantenLaden && <p className="mt-1 text-xs text-gray-400">Wird geladen…</p>}

            {!mandantenLaden && zuordenbare.length === 0 && (
              <p className="mt-1 text-xs text-gray-500">Keine Mandanten zum Zuordnen verfügbar.</p>
            )}

            <div className="mt-2 space-y-1">
              {zuordenbare.map((m) => (
                <label
                  key={m.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50"
                >
                  <input
                    type="checkbox"
                    checked={gewaehlt.includes(m.id)}
                    onChange={() => umschalten(m.id)}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-gray-900">{m.name}</span>
                </label>
              ))}
            </div>

            {gewaehlt.length === 0 && nichtSichtbare.length === 0 && !mandantenLaden && (
              <p className="mt-2 text-xs text-amber-700">
                Ohne Mandant kommt der Benutzer an keine Daten. Er kann sich anmelden und sieht dann
                einen entsprechenden Hinweis.
              </p>
            )}

            {nichtSichtbare.length > 0 && (
              <p className="mt-2 text-xs text-gray-500">
                Zusätzlich zugeordnet: {nichtSichtbare.map((m) => m.name).join(', ')} — diese
                Zuordnungen kannst du nicht ändern und sie bleiben beim Speichern erhalten.
              </p>
            )}
          </fieldset>

          {!istBearbeiten && (
            <p className="text-xs text-gray-500">
              Der Benutzer erhält eine Einladungs-E-Mail zum Setzen des Passworts.
            </p>
          )}

          {mutation.isError && (
            <p role="alert" className="text-sm text-red-500">
              {extractErrorMessage(
                mutation.error,
                istBearbeiten ? 'Fehler beim Speichern.' : 'Fehler beim Anlegen des Benutzers.',
              )}
            </p>
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
              disabled={isSubmitting || mutation.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {istBearbeiten ? 'Speichern' : 'Anlegen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
