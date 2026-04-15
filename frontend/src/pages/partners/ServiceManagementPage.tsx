import axios from 'axios'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import {
  createPartnerService,
  createServiceMatcher,
  deleteServiceMatcher,
  deleteService,
  listPartnerServices,
  previewServiceMatcher,
  updateService,
  updateServiceMatcher,
  type CreateServicePayload,
  type CreateServiceMatcherPayload,
  type MatcherPreviewResponse,
  type ServiceMatcherItem,
  type ServiceListItem,
  type UpdateServicePayload,
} from '@/api/services'
import { getPartner } from '@/api/partners'

const serviceTypeLabels: Record<'customer' | 'supplier' | 'employee' | 'shareholder' | 'authority' | 'internal_transfer' | 'unknown', string> = {
  customer: 'Kunde',
  supplier: 'Lieferant',
  employee: 'Mitarbeiter',
  shareholder: 'Gesellschafter',
  authority: 'Behörde',
  internal_transfer: 'Interne Umbuchung',
  unknown: 'Unbekannt',
}

type ServiceFormState = {
  name: string
  description: string
  service_type: 'customer' | 'supplier' | 'employee' | 'shareholder' | 'authority' | 'internal_transfer' | 'unknown'
  tax_rate: string
  erfolgsneutral: boolean
  valid_from: string
  valid_to: string
}

type MatcherFormState = {
  pattern: string
  pattern_type: 'string' | 'regex'
  internal_only: boolean
}

const emptyForm: ServiceFormState = {
  name: '',
  description: '',
  service_type: 'unknown',
  tax_rate: '20.00',
  erfolgsneutral: false,
  valid_from: '',
  valid_to: '',
}

const emptyMatcherForm: MatcherFormState = {
  pattern: '',
  pattern_type: 'string',
  internal_only: false,
}

function toFormState(service: ServiceListItem): ServiceFormState {
  return {
    name: service.name,
    description: service.description ?? '',
    service_type: service.service_type,
    tax_rate: service.tax_rate,
    erfolgsneutral: service.erfolgsneutral ?? false,
    valid_from: service.valid_from ?? '',
    valid_to: service.valid_to ?? '',
  }
}

function toCreatePayload(form: ServiceFormState): CreateServicePayload {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    service_type: form.service_type,
    tax_rate: form.tax_rate.trim(),
    erfolgsneutral: form.erfolgsneutral,
    valid_from: form.valid_from || null,
    valid_to: form.valid_to || null,
  }
}

function toUpdatePayload(form: ServiceFormState): UpdateServicePayload {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    service_type: form.service_type,
    tax_rate: form.tax_rate.trim(),
    erfolgsneutral: form.erfolgsneutral,
    valid_from: form.valid_from || null,
    valid_to: form.valid_to || null,
  }
}

function formatDateRange(service: ServiceListItem): string {
  if (!service.valid_from && !service.valid_to) {
    return 'Immer gültig'
  }

  if (service.valid_from && service.valid_to) {
    return `${service.valid_from} bis ${service.valid_to}`
  }

  if (service.valid_from) {
    return `Ab ${service.valid_from}`
  }

  return `Bis ${service.valid_to}`
}

export function ServiceManagementPage() {
  const { partnerId } = useParams<{ partnerId: string }>()
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const role = useAuthStore((s) => s.user?.role ?? '')
  const queryClient = useQueryClient()

  const [createForm, setCreateForm] = useState<ServiceFormState>(emptyForm)
  const [editingServiceId, setEditingServiceId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<ServiceFormState>(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [matcherError, setMatcherError] = useState<string | null>(null)
  const [createMatcherForms, setCreateMatcherForms] = useState<Record<string, MatcherFormState>>({})
  const [editingMatcherId, setEditingMatcherId] = useState<string | null>(null)
  const [editMatcherForm, setEditMatcherForm] = useState<MatcherFormState>(emptyMatcherForm)
  const [previewForServiceId, setPreviewForServiceId] = useState<string | null>(null)
  const [previewResult, setPreviewResult] = useState<MatcherPreviewResponse | null>(null)

  const isReadOnly = role === 'viewer'

  const { data: partner, isLoading: partnerLoading, isError: partnerError } = useQuery({
    queryKey: ['partner', mandantId, partnerId],
    queryFn: () => getPartner(mandantId, partnerId!),
    enabled: !!mandantId && !!partnerId,
  })

  const { data: services = [], isLoading: servicesLoading } = useQuery({
    queryKey: ['partner-services', mandantId, partnerId],
    queryFn: () => listPartnerServices(mandantId, partnerId!),
    enabled: !!mandantId && !!partnerId,
  })

  const refreshServices = async () => {
    await queryClient.invalidateQueries({ queryKey: ['partner-services', mandantId, partnerId] })
    await queryClient.invalidateQueries({ queryKey: ['partners', mandantId] })
  }

  const createMutation = useMutation({
    mutationFn: () => createPartnerService(mandantId, partnerId!, toCreatePayload(createForm)),
    onSuccess: async () => {
      setCreateForm(emptyForm)
      setFormError(null)
      setMatcherError(null)
      setNotice('Leistung gespeichert. Bitte prüfe die neu erzeugten Vorschläge in der Review-Queue.')
      await refreshServices()
    },
    onError: (error) => setFormError(extractErrorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: (serviceId: string) => updateService(mandantId, serviceId, toUpdatePayload(editForm)),
    onSuccess: async () => {
      setEditingServiceId(null)
      setFormError(null)
      setMatcherError(null)
      setNotice('Leistung aktualisiert. Bitte prüfe die neu erzeugten Vorschläge in der Review-Queue.')
      await refreshServices()
    },
    onError: (error) => setFormError(extractErrorMessage(error)),
  })

  const deleteMutation = useMutation({
    mutationFn: (serviceId: string) => deleteService(mandantId, serviceId),
    onSuccess: async () => {
      setFormError(null)
      setMatcherError(null)
      setNotice('Leistung gelöscht. Bitte prüfe die neu erzeugten Vorschläge in der Review-Queue.')
      await refreshServices()
    },
    onError: (error) => setFormError(extractErrorMessage(error)),
  })

  const createMatcherMutation = useMutation({
    mutationFn: ({ serviceId, payload }: { serviceId: string; payload: CreateServiceMatcherPayload }) =>
      createServiceMatcher(mandantId, serviceId, payload),
    onSuccess: async (_, variables) => {
      setCreateMatcherForms((current) => ({
        ...current,
        [variables.serviceId]: emptyMatcherForm,
      }))
      setPreviewResult(null)
      setPreviewForServiceId(null)
      setMatcherError(null)
      setFormError(null)
      setNotice('Matcher gespeichert. Buchungszeilen wurden automatisch neu zugewiesen.')
      await refreshServices()
    },
    onError: (error) => setMatcherError(extractErrorMessage(error)),
  })

  const updateMatcherMutation = useMutation({
    mutationFn: ({ serviceId, matcherId, payload }: { serviceId: string; matcherId: string; payload: CreateServiceMatcherPayload }) =>
      updateServiceMatcher(mandantId, serviceId, matcherId, payload),
    onSuccess: async () => {
      setEditingMatcherId(null)
      setEditMatcherForm(emptyMatcherForm)
      setMatcherError(null)
      setFormError(null)
      setNotice('Matcher aktualisiert. Buchungszeilen wurden automatisch neu zugewiesen.')
      await refreshServices()
    },
    onError: (error) => setMatcherError(extractErrorMessage(error)),
  })

  const deleteMatcherMutation = useMutation({
    mutationFn: ({ serviceId, matcherId }: { serviceId: string; matcherId: string }) =>
      deleteServiceMatcher(mandantId, serviceId, matcherId),
    onSuccess: async () => {
      setMatcherError(null)
      setFormError(null)
      setNotice('Matcher gelöscht. Bitte prüfe die neu erzeugten Vorschläge in der Review-Queue.')
      await refreshServices()
    },
    onError: (error) => setMatcherError(extractErrorMessage(error)),
  })

  const previewMatcherMutation = useMutation({
    mutationFn: ({ serviceId, payload }: { serviceId: string; payload: CreateServiceMatcherPayload }) =>
      previewServiceMatcher(mandantId, serviceId, payload),
    onSuccess: (data, variables) => {
      setPreviewForServiceId(variables.serviceId)
      setPreviewResult(data)
      setMatcherError(null)
    },
    onError: (error) => {
      setMatcherError(extractErrorMessage(error))
      setPreviewResult(null)
      setPreviewForServiceId(null)
    },
  })

  if (partnerLoading || servicesLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (partnerError || !partnerId || !partner) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">
        Partner nicht gefunden.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-2 text-sm text-gray-400">
        <Link to="/partners" className="hover:underline">Partner</Link>
        {' / '}
        <Link to={`/partners/${partnerId}`} className="hover:underline">{partner.display_name ?? partner.name}</Link>
        {' / Leistungen'}
      </div>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Leistungen verwalten</h1>
          <p className="mt-1 text-sm text-gray-500">
            Pflege von Leistungen, Geltungszeiträumen und Basisleistungs-Schutz für {partner.display_name ?? partner.name}.
          </p>
        </div>
        <Link
          to={`/partners/${partnerId}`}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
        >
          Zur Partneransicht
        </Link>
      </div>

      {notice && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {notice}
        </div>
      )}

      {formError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {formError}
        </div>
      )}

      {matcherError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {matcherError}
        </div>
      )}

      {!isReadOnly && partner.is_active && (
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-800">Neue Leistung</h2>
          <p className="mt-1 text-sm text-gray-500">Neue Leistungen können mit optionalem Geltungszeitraum angelegt werden. Ohne Datumsangaben ist die Leistung immer gültig.</p>
          <ServiceForm
            form={createForm}
            onChange={setCreateForm}
            onSubmit={() => createMutation.mutate()}
            submitLabel="Leistung anlegen"
            loading={createMutation.isPending}
          />
        </div>
      )}

      <div className="space-y-4">
        {services.map((service) => {
          const isEditing = editingServiceId === service.id

          return (
            <div key={service.id} className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-gray-900">{service.name}</h2>
                    {service.is_base_service && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        Basisleistung
                      </span>
                    )}
                  </div>
                  {service.description && (
                    <p className="mt-2 text-sm text-gray-600">{service.description}</p>
                  )}
                </div>
                <div className="text-right text-sm text-gray-500">
                  <div>Typ: {serviceTypeLabels[service.service_type]}</div>
                  <div>Steuer: {service.tax_rate}%</div>
                  <div>Erfolgsneutral: {service.erfolgsneutral ? 'Ja' : 'Nein'}</div>
                  <div>Zeitraum: {formatDateRange(service)}</div>
                  <div>Matcher: {service.matchers.length}</div>
                </div>
              </div>

              {isEditing ? (
                <div className="mt-5 border-t border-gray-100 pt-5">
                  <ServiceForm
                    form={editForm}
                    onChange={setEditForm}
                    onSubmit={() => updateMutation.mutate(service.id)}
                    submitLabel="Änderungen speichern"
                    loading={updateMutation.isPending}
                    disableName={service.is_base_service}
                    onCancel={() => {
                      setEditingServiceId(null)
                      setFormError(null)
                    }}
                  />
                </div>
              ) : (
                <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-4">
                  {!isReadOnly && partner.is_active && (
                    <>
                      <button
                        onClick={() => {
                          setNotice(null)
                          setFormError(null)
                          setMatcherError(null)
                          setEditingServiceId(service.id)
                          setEditForm(toFormState(service))
                        }}
                        className="rounded border border-blue-200 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50"
                      >
                        Bearbeiten
                      </button>
                      <button
                        onClick={() => {
                          if (service.is_base_service) {
                            setFormError('Die Basisleistung kann nicht gelöscht werden.')
                            return
                          }
                          const confirmed = window.confirm('Leistung wirklich löschen?')
                          if (!confirmed) return
                          setNotice(null)
                          setMatcherError(null)
                          deleteMutation.mutate(service.id)
                        }}
                        disabled={deleteMutation.isPending || service.is_base_service}
                        className="rounded border border-red-200 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Löschen
                      </button>
                    </>
                  )}
                  {service.is_base_service && (
                    <p className="text-xs text-gray-500">
                      Die Basisleistung bleibt erhalten und ihr Name ist nicht editierbar.
                    </p>
                  )}
                </div>
              )}

              <div className="mt-5 border-t border-gray-100 pt-5">
                <MatcherSection
                  service={service}
                  isReadOnly={isReadOnly || !partner.is_active}
                  createForm={createMatcherForms[service.id] ?? emptyMatcherForm}
                  onCreateFormChange={(next) => {
                    setCreateMatcherForms((current) => ({
                      ...current,
                      [service.id]: next,
                    }))
                    if (previewForServiceId === service.id) {
                      setPreviewResult(null)
                      setPreviewForServiceId(null)
                    }
                  }}
                  editingMatcherId={editingMatcherId}
                  editForm={editMatcherForm}
                  onStartEdit={(matcher) => {
                    setNotice(null)
                    setMatcherError(null)
                    setEditingMatcherId(matcher.id)
                    setEditMatcherForm({
                      pattern: matcher.pattern,
                      pattern_type: matcher.pattern_type,
                      internal_only: matcher.internal_only ?? false,
                    })
                  }}
                  onEditFormChange={setEditMatcherForm}
                  onCancelEdit={() => {
                    setEditingMatcherId(null)
                    setEditMatcherForm(emptyMatcherForm)
                    setMatcherError(null)
                  }}
                  onCreate={() => {
                    const payload = createMatcherForms[service.id] ?? emptyMatcherForm
                    setNotice(null)
                    setPreviewResult(null)
                    setPreviewForServiceId(null)
                    createMatcherMutation.mutate({
                      serviceId: service.id,
                      payload,
                    })
                  }}
                  onUpdate={(matcherId) => {
                    setNotice(null)
                    updateMatcherMutation.mutate({
                      serviceId: service.id,
                      matcherId,
                      payload: editMatcherForm,
                    })
                  }}
                  onDelete={(matcherId) => {
                    const confirmed = window.confirm('Matcher wirklich löschen?')
                    if (!confirmed) return
                    setNotice(null)
                    deleteMatcherMutation.mutate({ serviceId: service.id, matcherId })
                  }}
                  onPreview={() => {
                    const payload = createMatcherForms[service.id] ?? emptyMatcherForm
                    setNotice(null)
                    previewMatcherMutation.mutate({ serviceId: service.id, payload })
                  }}
                  previewResult={previewForServiceId === service.id ? previewResult : null}
                  previewLoading={previewMatcherMutation.isPending && previewMatcherMutation.variables?.serviceId === service.id}
                  busy={createMatcherMutation.isPending || updateMatcherMutation.isPending || deleteMatcherMutation.isPending}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function MatcherSection({
  service,
  isReadOnly,
  createForm,
  onCreateFormChange,
  editingMatcherId,
  editForm,
  onStartEdit,
  onEditFormChange,
  onCancelEdit,
  onCreate,
  onUpdate,
  onDelete,
  onPreview,
  previewResult,
  previewLoading,
  busy,
}: {
  service: ServiceListItem
  isReadOnly: boolean
  createForm: MatcherFormState
  onCreateFormChange: (next: MatcherFormState) => void
  editingMatcherId: string | null
  editForm: MatcherFormState
  onStartEdit: (matcher: ServiceMatcherItem) => void
  onEditFormChange: (next: MatcherFormState) => void
  onCancelEdit: () => void
  onCreate: () => void
  onUpdate: (matcherId: string) => void
  onDelete: (matcherId: string) => void
  onPreview: () => void
  previewResult: MatcherPreviewResponse | null
  previewLoading: boolean
  busy: boolean
}) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Matcher</h3>
          <p className="text-xs text-gray-500">
            String-Matcher suchen case-insensitiv per Textsuche, Regex-Matcher werden serverseitig validiert.
          </p>
        </div>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
          {service.matchers.length} Einträge
        </span>
      </div>

      {service.matchers.length === 0 ? (
        <p className="text-sm text-gray-400">Noch keine Matcher hinterlegt.</p>
      ) : (
        <div className="space-y-2">
          {service.matchers.map((matcher) => {
            const isEditingMatcher = editingMatcherId === matcher.id
            return (
              <div key={matcher.id} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-3">
                {isEditingMatcher ? (
                  <MatcherForm
                    form={editForm}
                    onChange={onEditFormChange}
                    onSubmit={() => onUpdate(matcher.id)}
                    submitLabel="Matcher speichern"
                    loading={busy}
                    onCancel={onCancelEdit}
                  />
                ) : (
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <code className="font-mono text-sm text-gray-800">{matcher.pattern}</code>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${matcher.pattern_type === 'regex' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>
                          {matcher.pattern_type === 'regex' ? 'Regex' : 'String'}
                        </span>
                        {matcher.internal_only && (
                          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                            Partner-intern
                          </span>
                        )}
                      </div>
                    </div>
                    {!isReadOnly && !service.is_base_service && (
                      <div className="flex gap-2">
                        <button
                          onClick={() => onStartEdit(matcher)}
                          aria-label={`Matcher ${matcher.pattern} bearbeiten`}
                          className="rounded border border-blue-200 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
                        >
                          Bearbeiten
                        </button>
                        <button
                          onClick={() => onDelete(matcher.id)}
                          aria-label={`Matcher ${matcher.pattern} löschen`}
                          disabled={busy}
                          className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                        >
                          Löschen
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {!isReadOnly && !service.is_base_service && (
        <div className="mt-4 rounded-lg border border-dashed border-gray-300 p-4">
          <h4 className="text-sm font-semibold text-gray-800">Neuen Matcher anlegen</h4>
          <MatcherForm
            form={createForm}
            onChange={onCreateFormChange}
            onSubmit={onCreate}
            submitLabel="Matcher anlegen"
            loading={busy}
            onTest={onPreview}
            testLoading={previewLoading}
            hasTested={previewResult !== null}
          />
          {previewResult !== null && (
            <div className="mt-4">
              <p className="text-sm font-medium text-gray-700">
                Vorschau: {previewResult.total === 0
                  ? 'Kein Treffer — es würden keine Buchungszeilen neu dieser Leistung zugeordnet.'
                  : `${previewResult.total} Buchungszeile${previewResult.total !== 1 ? 'n' : ''} würde${previewResult.total !== 1 ? 'n' : ''} neu dieser Leistung zugeordnet`}
              </p>
              {previewResult.matched_lines.length > 0 && (
                <div className="mt-2 overflow-x-auto rounded border border-gray-200">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold text-gray-500">Hinweis</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-500">Datum</th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-500">Betrag</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-500">Text</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-500">Leistung</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-500">Aktueller Partner</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-500">Buchungsname</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {[...previewResult.matched_lines]
                        .sort((a, b) => Number(b.has_conflicting_partner_criteria) - Number(a.has_conflicting_partner_criteria))
                        .map((line) => (
                        <tr key={line.journal_line_id} className={line.has_conflicting_partner_criteria ? 'bg-red-50/40 hover:bg-red-50' : 'hover:bg-gray-50'}>
                          <td className="whitespace-nowrap px-3 py-2">
                            {line.has_conflicting_partner_criteria ? (
                              <span className="rounded bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-700" title={line.conflicting_partner_criteria.join(', ')}>
                                Widerspruch
                              </span>
                            ) : (
                              <span className="font-semibold text-green-700" title="Kein Widerspruch">✓</span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-gray-700">{line.booking_date}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-gray-700">
                            {parseFloat(line.amount).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {line.currency}
                          </td>
                          <td className="max-w-[200px] truncate px-3 py-2 text-gray-600">{line.text ?? '–'}</td>
                          <td className="px-3 py-2 text-gray-700">{line.current_service_name ?? '–'}</td>
                          <td className="px-3 py-2 text-gray-700">{line.current_partner_name ?? '–'}</td>
                          <td className="px-3 py-2 text-gray-500">{line.partner_name_raw ?? '–'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {service.is_base_service && (
        <p className="mt-3 text-xs text-gray-500">Für die Basisleistung sind keine Matcher erlaubt.</p>
      )}
    </div>
  )
}

function MatcherForm({
  form,
  onChange,
  onSubmit,
  submitLabel,
  loading,
  onCancel,
  onTest,
  testLoading,
  hasTested = true,
}: {
  form: MatcherFormState
  onChange: (next: MatcherFormState) => void
  onSubmit: () => void
  submitLabel: string
  loading: boolean
  onCancel?: () => void
  onTest?: () => void
  testLoading?: boolean
  hasTested?: boolean
}) {
  const requiresPreview = !!onTest
  const canSubmit = !loading && !!form.pattern.trim() && (!requiresPreview || hasTested)

  return (
    <div className="mt-3">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Pattern</span>
          <input
            value={form.pattern}
            onChange={(event) => onChange({ ...form, pattern: event.target.value })}
            placeholder="z. B. hosting oder ^AWS"
            className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>
        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Typ</span>
          <select
            value={form.pattern_type}
            onChange={(event) => onChange({ ...form, pattern_type: event.target.value as MatcherFormState['pattern_type'] })}
            className="w-full rounded border px-3 py-2 text-sm"
          >
            <option value="string">String</option>
            <option value="regex">Regex</option>
          </select>
        </label>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-gray-600">
        <input
          type="checkbox"
          checked={form.internal_only}
          onChange={(event) => onChange({ ...form, internal_only: event.target.checked })}
          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />
        <span>Nur Partner-interne Buchungen verschieben</span>
      </label>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitLabel}
        </button>
        {onTest && (
          <button
            onClick={onTest}
            disabled={testLoading || !form.pattern.trim()}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {testLoading ? 'Wird geprüft…' : 'Matcher testen'}
          </button>
        )}
        {onCancel && (
          <button
            onClick={onCancel}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            Abbrechen
          </button>
        )}
      </div>
    </div>
  )
}

function ServiceForm({
  form,
  onChange,
  onSubmit,
  submitLabel,
  loading,
  disableName = false,
  onCancel,
}: {
  form: ServiceFormState
  onChange: (next: ServiceFormState) => void
  onSubmit: () => void
  submitLabel: string
  loading: boolean
  disableName?: boolean
  onCancel?: () => void
}) {
  const isDateInvalid = !!form.valid_from && !!form.valid_to && form.valid_from > form.valid_to

  return (
    <div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Name</span>
          <input
            value={form.name}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
            disabled={disableName}
            placeholder="z. B. Hosting"
            className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-gray-100"
          />
        </label>

        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Typ</span>
          <select
            value={form.service_type}
            onChange={(event) => onChange({ ...form, service_type: event.target.value as ServiceFormState['service_type'] })}
            className="w-full rounded border px-3 py-2 text-sm"
          >
            {Object.entries(serviceTypeLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>

        <label className="text-sm text-gray-600 md:col-span-2">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Beschreibung</span>
          <input
            value={form.description}
            onChange={(event) => onChange({ ...form, description: event.target.value })}
            placeholder="Optional"
            className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Steuersatz</span>
          <input
            value={form.tax_rate}
            onChange={(event) => onChange({ ...form, tax_rate: event.target.value })}
            placeholder="20.00"
            inputMode="decimal"
            className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="flex items-center gap-2 text-sm text-gray-600 md:col-span-2">
          <input
            type="checkbox"
            checked={form.erfolgsneutral}
            onChange={(event) => onChange({ ...form, erfolgsneutral: event.target.checked })}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span>Erfolgsneutral</span>
        </label>

        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Gültig ab</span>
          <input
            type="date"
            value={form.valid_from}
            onChange={(event) => onChange({ ...form, valid_from: event.target.value })}
            className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="text-sm text-gray-600">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Gültig bis</span>
          <input
            type="date"
            value={form.valid_to}
            onChange={(event) => onChange({ ...form, valid_to: event.target.value })}
            className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>
      </div>

      <p className="mt-3 text-xs text-gray-500">
        Leer gelassene Datumsfelder bedeuten: immer gültig.
      </p>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => onChange({ ...form, valid_from: '', valid_to: '' })}
          disabled={!form.valid_from && !form.valid_to}
          className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Auf immer gültig zurücksetzen
        </button>
      </div>

      {isDateInvalid && (
        <p className="mt-3 text-sm text-red-600">Das Enddatum muss nach oder gleich dem Startdatum liegen.</p>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={onSubmit}
          disabled={loading || !form.name.trim() || isDateInvalid}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            Abbrechen
          </button>
        )}
      </div>
    </div>
  )
}

function extractErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return 'Die Änderung konnte nicht gespeichert werden.'
  }

  const detail = error.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail.map((entry) => entry.msg).filter(Boolean).join(', ')
  }

  return 'Die Änderung konnte nicht gespeichert werden.'
}