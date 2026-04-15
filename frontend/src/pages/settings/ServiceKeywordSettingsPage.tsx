import axios from 'axios'
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createServiceKeyword,
  deleteServiceKeyword,
  listServiceKeywords,
  updateServiceKeyword,
  type CreateServiceTypeKeywordPayload,
  type KeywordTargetType,
  type ServiceTypeKeywordItem,
} from '@/api/services'
import { useAuthStore } from '@/store/auth-store'

type KeywordFormState = {
  pattern: string
  pattern_type: 'string' | 'regex'
  target_service_type: KeywordTargetType
}

const emptyForm: KeywordFormState = {
  pattern: '',
  pattern_type: 'string',
  target_service_type: 'employee',
}

const targetLabels = {
  employee: 'Mitarbeiter',
  shareholder: 'Gesellschafter',
  authority: 'Behörde',
} as const

function validateRegex(pattern: string, patternType: 'string' | 'regex'): string | null {
  if (patternType !== 'regex' || !pattern.trim()) {
    return null
  }

  try {
    new RegExp(pattern)
    return null
  } catch (error) {
    return error instanceof Error ? error.message : 'Ungültiger Regex-Ausdruck'
  }
}

function toPayload(form: KeywordFormState): CreateServiceTypeKeywordPayload {
  return {
    pattern: form.pattern.trim(),
    pattern_type: form.pattern_type,
    target_service_type: form.target_service_type,
  }
}

export function ServiceKeywordSettingsPage() {
  const mandantId = useAuthStore((state) => state.user?.mandant_id ?? '')
  const queryClient = useQueryClient()
  const [createForm, setCreateForm] = useState<KeywordFormState>(emptyForm)
  const [editingKeywordId, setEditingKeywordId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<KeywordFormState>(emptyForm)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['service-keywords', mandantId],
    queryFn: () => listServiceKeywords(mandantId),
    enabled: !!mandantId,
  })

  const groupedItems = useMemo(() => {
    const items = data?.items ?? []
    return {
      employee: items.filter((item) => item.target_service_type === 'employee'),
      shareholder: items.filter((item) => item.target_service_type === 'shareholder'),
      authority: items.filter((item) => item.target_service_type === 'authority'),
    }
  }, [data])

  const createRegexError = validateRegex(createForm.pattern, createForm.pattern_type)
  const editRegexError = validateRegex(editForm.pattern, editForm.pattern_type)

  const refreshKeywords = async (message: string) => {
    await queryClient.invalidateQueries({ queryKey: ['service-keywords', mandantId] })
    setNotice({ tone: 'success', message })
  }

  const createMutation = useMutation({
    mutationFn: () => createServiceKeyword(mandantId, toPayload(createForm)),
    onSuccess: async () => {
      setCreateForm(emptyForm)
      await refreshKeywords('Keyword-Regel gespeichert. Änderungen wirken auf künftige automatische Typ-Ermittlungen.')
    },
    onError: (error) => setNotice({ tone: 'error', message: extractErrorMessage(error) }),
  })

  const updateMutation = useMutation({
    mutationFn: (keywordId: string) => updateServiceKeyword(mandantId, keywordId, toPayload(editForm)),
    onSuccess: async () => {
      setEditingKeywordId(null)
      setEditForm(emptyForm)
      await refreshKeywords('Keyword-Regel aktualisiert. Änderungen wirken auf künftige automatische Typ-Ermittlungen.')
    },
    onError: (error) => setNotice({ tone: 'error', message: extractErrorMessage(error) }),
  })

  const deleteMutation = useMutation({
    mutationFn: (keywordId: string) => deleteServiceKeyword(mandantId, keywordId),
    onSuccess: async () => {
      await refreshKeywords('Keyword-Regel gelöscht. Änderungen wirken auf künftige automatische Typ-Ermittlungen.')
    },
    onError: (error) => setNotice({ tone: 'error', message: extractErrorMessage(error) }),
  })

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">
        Keyword-Regeln konnten nicht geladen werden.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Einstellungen</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Service-Keywords</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
          Pflege mandantenspezifischer Begriffe für die automatische Erkennung von Mitarbeiter-, Gesellschafter- und Behörden-Leistungen.
        </p>
      </div>

      {notice ? (
        <div className={`mb-4 rounded-xl px-4 py-3 text-sm ${notice.tone === 'success' ? 'border border-emerald-200 bg-emerald-50 text-emerald-700' : 'border border-red-200 bg-red-50 text-red-700'}`}>
          {notice.message}
        </div>
      ) : null}

      <div className="mb-6 rounded-[1.5rem] border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">Neue Regel</h2>
        <p className="mt-1 text-sm text-slate-500">String-Regeln suchen case-insensitiv per Textsuche, Regex-Regeln werden vor dem Speichern validiert.</p>
        <KeywordForm
          form={createForm}
          onChange={setCreateForm}
          onSubmit={() => {
            setNotice(null)
            createMutation.mutate()
          }}
          submitLabel="Regel anlegen"
          loading={createMutation.isPending}
          regexError={createRegexError}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {(['employee', 'shareholder', 'authority'] as const).map((targetType) => (
          <section key={targetType} className="rounded-[1.5rem] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">{targetLabels[targetType]}</h2>
                <p className="mt-1 text-sm text-slate-500">Mandantenspezifische Regeln für {targetLabels[targetType].toLowerCase()}.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
                {groupedItems[targetType].length} Regeln
              </span>
            </div>

            <div className="space-y-3">
              {groupedItems[targetType].length === 0 ? (
                <p className="text-sm text-slate-400">Noch keine eigenen Regeln hinterlegt.</p>
              ) : (
                groupedItems[targetType].map((item) => {
                  const isEditing = editingKeywordId === item.id
                  return (
                    <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      {isEditing ? (
                        <KeywordForm
                          form={editForm}
                          onChange={setEditForm}
                          onSubmit={() => {
                            setNotice(null)
                            updateMutation.mutate(item.id)
                          }}
                          submitLabel="Regel speichern"
                          loading={updateMutation.isPending}
                          regexError={editRegexError}
                          onCancel={() => {
                            setEditingKeywordId(null)
                            setEditForm(emptyForm)
                          }}
                        />
                      ) : (
                        <KeywordRuleRow
                          item={item}
                          onEdit={() => {
                            setNotice(null)
                            setEditingKeywordId(item.id)
                            setEditForm({
                              pattern: item.pattern,
                              pattern_type: item.pattern_type,
                              target_service_type: item.target_service_type,
                            })
                          }}
                          onDelete={() => {
                            if (!globalThis.confirm('Regel wirklich löschen?')) return
                            setNotice(null)
                            deleteMutation.mutate(item.id)
                          }}
                          busy={deleteMutation.isPending}
                        />
                      )}
                    </div>
                  )
                })
              )}
            </div>

            <div className="mt-5 border-t border-slate-200 pt-4">
              <h3 className="text-sm font-semibold text-slate-700">System-Defaults</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {data?.system_defaults
                  .filter((item) => item.target_service_type === targetType)
                  .map((item, index) => (
                    <span key={`${item.target_service_type}-${item.pattern}-${index}`} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                      {item.pattern} · {item.pattern_type === 'regex' ? 'Regex' : 'String'}
                    </span>
                  ))}
              </div>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

function KeywordRuleRow({
  item,
  onEdit,
  onDelete,
  busy,
}: Readonly<{
  item: ServiceTypeKeywordItem
  onEdit: () => void
  onDelete: () => void
  busy: boolean
}>) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <div className="flex items-center gap-2">
          <code className="font-mono text-sm text-slate-900">{item.pattern}</code>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${item.pattern_type === 'regex' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>
            {item.pattern_type === 'regex' ? 'Regex' : 'String'}
          </span>
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={onEdit}
          className="rounded border border-blue-200 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
        >
          Bearbeiten
        </button>
        <button
          onClick={onDelete}
          disabled={busy}
          className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
        >
          Löschen
        </button>
      </div>
    </div>
  )
}

function KeywordForm({
  form,
  onChange,
  onSubmit,
  submitLabel,
  loading,
  regexError,
  onCancel,
}: Readonly<{
  form: KeywordFormState
  onChange: (next: KeywordFormState) => void
  onSubmit: () => void
  submitLabel: string
  loading: boolean
  regexError: string | null
  onCancel?: () => void
}>) {
  const patternInputId = onCancel ? 'edit-keyword-pattern' : 'create-keyword-pattern'
  const patternTypeSelectId = onCancel ? 'edit-keyword-pattern-type' : 'create-keyword-pattern-type'
  const targetTypeSelectId = onCancel ? 'edit-keyword-target-type' : 'create-keyword-target-type'

  return (
    <div className="mt-4">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px_180px]">
        <label htmlFor={patternInputId} className="text-sm text-slate-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Pattern</span>
          <input
            id={patternInputId}
            value={form.pattern}
            onChange={(event) => onChange({ ...form, pattern: event.target.value })}
            placeholder="z. B. Gehalt oder ^Finanzamt"
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
          />
        </label>

        <label htmlFor={patternTypeSelectId} className="text-sm text-slate-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Typ</span>
          <select
            id={patternTypeSelectId}
            value={form.pattern_type}
            onChange={(event) => onChange({ ...form, pattern_type: event.target.value as KeywordFormState['pattern_type'] })}
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
          >
            <option value="string">String</option>
            <option value="regex">Regex</option>
          </select>
        </label>

        <label htmlFor={targetTypeSelectId} className="text-sm text-slate-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Zieltyp</span>
          <select
            id={targetTypeSelectId}
            value={form.target_service_type}
            onChange={(event) => onChange({ ...form, target_service_type: event.target.value as KeywordFormState['target_service_type'] })}
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
          >
            <option value="employee">Mitarbeiter</option>
            <option value="shareholder">Gesellschafter</option>
            <option value="authority">Behörde</option>
          </select>
        </label>
      </div>

      {regexError ? (
        <p className="mt-3 text-sm text-red-600">Ungültige Regex: {regexError}</p>
      ) : null}

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={onSubmit}
          disabled={loading || !form.pattern.trim() || !!regexError}
          className="rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
        >
          {submitLabel}
        </button>
        {onCancel ? (
          <button
            onClick={onCancel}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100"
          >
            Abbrechen
          </button>
        ) : null}
      </div>
    </div>
  )
}

function extractErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return 'Die Keyword-Regel konnte nicht gespeichert werden.'
  }

  const detail = error.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail.map((entry) => entry.msg).filter(Boolean).join(', ')
  }

  return 'Die Keyword-Regel konnte nicht gespeichert werden.'
}