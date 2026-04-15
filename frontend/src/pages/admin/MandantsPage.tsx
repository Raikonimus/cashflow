import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  createMandant,
  executeMandantCleanup,
  getMandantCleanupPreview,
  listMandants,
  type CleanupPreviewSection,
} from '@/api/users'
import { selectMandant } from '@/api/auth'
import { useAuthStore } from '@/store/auth-store'

const schema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(255),
})

type FormValues = z.infer<typeof schema>
type CleanupScope = 'journal_data' | 'partner_service_data' | 'audit_data' | 'review_data'

export function MandantsPage() {
  const [showForm, setShowForm] = useState(false)
  const [configMandantId, setConfigMandantId] = useState<string | null>(null)
  const [selectedScopes, setSelectedScopes] = useState<CleanupScope[]>([])
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { selectMandant: storeSelect } = useAuthStore()

  const { data: mandants = [], isLoading, isError } = useQuery({
    queryKey: ['mandants'],
    queryFn: listMandants,
  })

  const { data: cleanupPreview } = useQuery({
    queryKey: ['mandant-cleanup-preview', configMandantId],
    queryFn: () => getMandantCleanupPreview(configMandantId!),
    enabled: !!configMandantId,
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
      const mandant = mandants.find((entry) => entry.id === id)
      if (mandant) {
        storeSelect({ id: mandant.id, name: mandant.name }, data.access_token)
      }
      navigate('/')
    },
  })

  const cleanupMutation = useMutation({
    mutationFn: ({ mandantId, mode, scopes }: { mandantId: string; mode: 'delete_mandant' | 'delete_data' | 'selected'; scopes?: CleanupScope[] }) =>
      executeMandantCleanup(mandantId, { mode, scopes }),
    onSuccess: (result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['mandants'] })
      queryClient.invalidateQueries({ queryKey: ['mandant-cleanup-preview', variables.mandantId] })
      setSelectedScopes([])
      setNotice({
        tone: 'success',
        message: result.deleted_mandant
          ? 'Mandant und alle zugehörigen Daten wurden gelöscht.'
          : 'Die ausgewählten Mandantendaten wurden gelöscht.',
      })
      if (result.deleted_mandant) {
        setConfigMandantId(null)
      }
    },
    onError: () => {
      setNotice({ tone: 'error', message: 'Die Löschaktion konnte nicht ausgeführt werden.' })
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
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Mandanten</h1>
        <button
          onClick={() => setShowForm((current) => !current)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {showForm ? 'Abbrechen' : '+ Neuer Mandant'}
        </button>
      </div>

      {notice ? (
        <div className={`mb-4 rounded-xl px-4 py-3 text-sm ${notice.tone === 'success' ? 'border border-emerald-200 bg-emerald-50 text-emerald-700' : 'border border-red-200 bg-red-50 text-red-700'}`}>
          {notice.message}
        </div>
      ) : null}

      {showForm && (
        <form
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
          className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
        >
          <div className="flex gap-3">
            <div className="flex-1">
              <input
                {...register('name')}
                placeholder="Mandantenname"
                className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {errors.name ? <p className="mt-1 text-xs text-red-500">{errors.name.message}</p> : null}
            </div>
            <button
              type="submit"
              disabled={isSubmitting || mutation.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
          {mutation.isError ? <p className="mt-2 text-sm text-red-500">Fehler beim Anlegen.</p> : null}
        </form>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Erstellt</th>
              <th className="px-4 py-3 text-left">Konfiguration</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {mandants.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                  Keine Mandanten vorhanden.
                </td>
              </tr>
            ) : null}
            {mandants.map((mandant) => (
              <MandantRow
                key={mandant.id}
                mandant={mandant}
                isOpen={configMandantId === mandant.id}
                cleanupPreview={configMandantId === mandant.id ? cleanupPreview : undefined}
                selectedScopes={selectedScopes}
                busy={cleanupMutation.isPending}
                onToggle={() => {
                  setNotice(null)
                  setSelectedScopes([])
                  setConfigMandantId((current) => (current === mandant.id ? null : mandant.id))
                }}
                onScopeToggle={(scope, checked) => {
                  setSelectedScopes((current) => checked ? [...current, scope] : current.filter((item) => item !== scope))
                }}
                onDeleteMandant={() => {
                  if (!cleanupPreview) return
                  if (!globalThis.confirm(`Mandant ${cleanupPreview.mandant_name} inklusive aller Daten wirklich löschen?`)) return
                  cleanupMutation.mutate({ mandantId: mandant.id, mode: 'delete_mandant' })
                }}
                onDeleteData={() => {
                  if (!cleanupPreview) return
                  if (!globalThis.confirm(`Alle Daten von ${cleanupPreview.mandant_name} löschen und den Mandanten behalten?`)) return
                  cleanupMutation.mutate({ mandantId: mandant.id, mode: 'delete_data' })
                }}
                onDeleteSelected={() => {
                  if (!cleanupPreview) return
                  if (!globalThis.confirm(`Die ausgewählten Datenblöcke von ${cleanupPreview.mandant_name} wirklich löschen?`)) return
                  cleanupMutation.mutate({ mandantId: mandant.id, mode: 'selected', scopes: selectedScopes })
                }}
                onEnter={() => enterMandant.mutate(mandant.id)}
                enterDisabled={enterMandant.isPending}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MandantRow({
  mandant,
  isOpen,
  cleanupPreview,
  selectedScopes,
  busy,
  onToggle,
  onScopeToggle,
  onDeleteMandant,
  onDeleteData,
  onDeleteSelected,
  onEnter,
  enterDisabled,
}: Readonly<{
  mandant: { id: string; name: string; is_active: boolean; created_at: string }
  isOpen: boolean
  cleanupPreview?: {
    mandant_name: string
    delete_mandant: CleanupPreviewSection
    delete_data: CleanupPreviewSection
    selectable_sections: CleanupPreviewSection[]
  }
  selectedScopes: CleanupScope[]
  busy: boolean
  onToggle: () => void
  onScopeToggle: (scope: CleanupScope, checked: boolean) => void
  onDeleteMandant: () => void
  onDeleteData: () => void
  onDeleteSelected: () => void
  onEnter: () => void
  enterDisabled: boolean
}>) {
  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-4 py-3 font-medium text-gray-900">{mandant.name}</td>
        <td className="px-4 py-3">
          <span className={`rounded px-2 py-1 text-xs font-medium ${mandant.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
            {mandant.is_active ? 'Aktiv' : 'Inaktiv'}
          </span>
        </td>
        <td className="px-4 py-3 text-gray-400">
          {new Date(mandant.created_at + 'Z').toLocaleDateString('de-DE', { timeZone: 'Europe/Vienna' })}
        </td>
        <td className="px-4 py-3">
          <button
            onClick={onToggle}
            className="rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            Konfiguration
          </button>
        </td>
        <td className="px-4 py-3 text-right">
          <button
            onClick={onEnter}
            disabled={enterDisabled}
            className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Einsteigen
          </button>
        </td>
      </tr>
      {isOpen ? (
        <tr>
          <td colSpan={5} className="bg-red-50/40 px-4 py-5">
            {cleanupPreview ? (
              <div className="space-y-5 rounded-xl border border-red-100 bg-white p-5 shadow-sm">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Mandantendetail-Konfiguration</h2>
                  <p className="mt-1 text-sm text-gray-600">Vor jeder Aktion wird konkret aufgelistet, welche Datensätze dieses Mandanten gelöscht werden.</p>
                </div>

                <CleanupCard
                  section={cleanupPreview.delete_mandant}
                  actionLabel="Mandanten vollständig löschen"
                  actionClassName="bg-red-700 hover:bg-red-800"
                  disabled={busy}
                  onAction={onDeleteMandant}
                />

                <CleanupCard
                  section={cleanupPreview.delete_data}
                  actionLabel="Nur Mandantendaten löschen"
                  actionClassName="bg-red-600 hover:bg-red-700"
                  disabled={busy}
                  onAction={onDeleteData}
                />

                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <h3 className="text-base font-semibold text-amber-900">Ausgewählte Daten löschen</h3>
                  <p className="mt-1 text-sm text-amber-800">Diese Aktion löscht nur die ausgewählten Datenblöcke dieses Mandanten.</p>
                  <div className="mt-4 space-y-4">
                    {cleanupPreview.selectable_sections.map((section) => {
                      const scope = section.key as CleanupScope
                      const checked = selectedScopes.includes(scope)
                      return (
                        <label key={section.key} className="block rounded-lg border border-amber-200 bg-white p-3">
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => onScopeToggle(scope, event.target.checked)}
                              className="mt-1 h-4 w-4 rounded border-amber-300"
                            />
                            <div className="flex-1">
                              <div className="text-sm font-semibold text-gray-900">{section.label}</div>
                              <div className="mt-1 text-sm text-gray-600">{section.description}</div>
                              <CleanupItemList items={section.items} />
                            </div>
                          </div>
                        </label>
                      )
                    })}
                  </div>
                  <button
                    onClick={onDeleteSelected}
                    disabled={busy || selectedScopes.length === 0}
                    className="mt-4 rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                  >
                    Ausgewählte Daten löschen
                  </button>
                </div>
              </div>
            ) : (
              <div className="py-4 text-sm text-gray-500">Konfiguration wird geladen…</div>
            )}
          </td>
        </tr>
      ) : null}
    </>
  )
}

function CleanupCard({
  section,
  actionLabel,
  actionClassName,
  disabled,
  onAction,
}: Readonly<{
  section: CleanupPreviewSection
  actionLabel: string
  actionClassName: string
  disabled: boolean
  onAction: () => void
}>) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4">
      <h3 className="text-base font-semibold text-red-900">{section.label}</h3>
      <p className="mt-1 text-sm text-red-800">{section.description}</p>
      <CleanupItemList items={section.items} />
      <button
        onClick={onAction}
        disabled={disabled}
        className={`mt-4 rounded px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${actionClassName}`}
      >
        {actionLabel}
      </button>
    </div>
  )
}

function CleanupItemList({ items }: Readonly<{ items: Array<{ key: string; label: string; count: number }> }>) {
  return (
    <ul className="mt-3 space-y-1 text-sm text-gray-700">
      {items.length === 0
        ? <li>Keine Datensätze betroffen.</li>
        : items.map((item) => <li key={item.key}>{item.label}: {item.count}</li>)}
    </ul>
  )
}
