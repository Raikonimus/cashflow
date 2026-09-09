import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listUnidentifiedGroups, resolveUnidentifiedGroup } from '@/api/review'
import type { ResolveGroupRequest, UnidentifiedGroup, UnidentifiedGroupLine } from '@/api/review'
import { listPartners } from '@/api/partners'
import { listPartnerServices } from '@/api/services'
import { extractErrorMessage } from '@/api/errors'
import { useAuthStore } from '@/store/auth-store'

/**
 * Fasst offene "kein Partner erkannt"-Einträge nach Händler zusammen.
 *
 * Ein Kartenimport erzeugt hunderte Einzelfälle, die sich auf wenige
 * wiederkehrende Händler verteilen. Pro Gruppe legt ein Klick Partner,
 * Leistung und Matcher an und ordnet alle Zeilen zu — und der Matcher greift
 * danach auch bei künftigen Importen.
 *
 * Der Händlername aus dem Buchungstext lautet oft anders als der bereits
 * gepflegte Partner ("MSFT" vs. "Microsoft Ireland"). Deshalb lässt sich
 * statt eines neuen Partners auch ein bestehender auswählen — und dann eine
 * seiner vorhandenen Leistungen, statt eine weitere anzulegen.
 */

const FIELD_CLASS =
  'mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400'
const HINT_CLASS = 'mt-1 block text-[11px] leading-4 text-slate-400'
const LABEL_CLASS = 'text-xs font-medium text-slate-600'

function formatMoney(value: string): string {
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) {
    return value
  }
  return numeric.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(value: string): string {
  const [year, month, day] = value.split('-')
  return day && month && year ? `${day}.${month}.${year}` : value
}

/** Bestehender Partner, egal ob gesucht oder vom Server vorgeschlagen. */
interface PartnerRef {
  id: string
  name: string
}

/** Entweder ein neuer Partner (Name) oder ein bestehender (Auswahl). */
type PartnerChoice =
  | { mode: 'new'; name: string }
  | { mode: 'existing'; partner: PartnerRef | null; suggested?: boolean }

interface GroupFormState {
  partner: PartnerChoice
  /** Leere Kennung bedeutet: neue Leistung mit serviceName anlegen. */
  serviceId: string
  serviceName: string
  pattern: string
}

function ModeToggle({
  groupKey,
  mode,
  onSelect,
}: Readonly<{
  groupKey: string
  mode: PartnerChoice['mode']
  onSelect: (mode: PartnerChoice['mode']) => void
}>) {
  const options: { value: PartnerChoice['mode']; label: string }[] = [
    { value: 'new', label: 'Neu anlegen' },
    { value: 'existing', label: 'Bestehender' },
  ]
  return (
    <div className="mt-1 flex gap-0.5 rounded-lg bg-slate-100 p-0.5">
      {options.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          aria-pressed={mode === value}
          aria-label={`${label} für ${groupKey}`}
          onClick={() => onSelect(value)}
          className={`flex-1 rounded-md px-2 py-1 text-[11px] font-medium ${
            mode === value
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function PartnerPicker({
  groupKey,
  mandantId,
  partner,
  onSelect,
}: Readonly<{
  groupKey: string
  mandantId: string
  partner: PartnerRef | null
  onSelect: (partner: PartnerRef | null) => void
}>) {
  const [query, setQuery] = useState('')
  const trimmed = query.trim()

  const { data: results = [], isFetching } = useQuery({
    queryKey: ['partner-search', mandantId, trimmed],
    queryFn: async () => {
      const page = await listPartners(mandantId, 1, 8, false, trimmed)
      return page.items.filter((item) => item.is_active)
    },
    enabled: !!mandantId && trimmed.length >= 2,
  })

  if (partner) {
    return (
      <div className="mt-1 flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5">
        <span className="truncate text-sm text-slate-900">{partner.name}</span>
        <button
          type="button"
          onClick={() => onSelect(null)}
          className="shrink-0 text-[11px] font-medium text-slate-500 hover:text-slate-700 hover:underline"
        >
          Ändern
        </button>
      </div>
    )
  }

  return (
    <>
      <input
        value={query}
        aria-label={`Partner suchen für ${groupKey}`}
        placeholder="Partner suchen…"
        onChange={(event) => setQuery(event.target.value)}
        className={FIELD_CLASS}
      />
      {trimmed.length >= 2 && results.length === 0 && !isFetching && (
        <p className="mt-1 text-[11px] text-slate-400">Kein aktiver Partner gefunden.</p>
      )}
      {results.length > 0 && (
        <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto">
          {results.map((candidate) => (
            <li key={candidate.id}>
              <button
                type="button"
                onClick={() => onSelect({ id: candidate.id, name: candidate.name })}
                className="block w-full truncate rounded-md px-2 py-1 text-left text-sm text-slate-700 hover:bg-slate-100"
              >
                {candidate.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function PartnerField({
  groupKey,
  mandantId,
  choice,
  onChange,
}: Readonly<{
  groupKey: string
  mandantId: string
  choice: PartnerChoice
  onChange: (next: PartnerChoice) => void
}>) {
  return (
    <div>
      <span className={LABEL_CLASS}>Partner</span>
      <ModeToggle
        groupKey={groupKey}
        mode={choice.mode}
        onSelect={(mode) =>
          onChange(mode === 'new' ? { mode: 'new', name: '' } : { mode: 'existing', partner: null })
        }
      />
      {choice.mode === 'new' ? (
        <>
          <input
            value={choice.name}
            aria-label={`Partner für ${groupKey}`}
            onChange={(event) => onChange({ mode: 'new', name: event.target.value })}
            className={FIELD_CLASS}
          />
          <span className={HINT_CLASS}>
            Bestehender Partner mit exakt diesem Namen wird wiederverwendet.
          </span>
        </>
      ) : (
        <>
          <PartnerPicker
            groupKey={groupKey}
            mandantId={mandantId}
            partner={choice.partner}
            onSelect={(partner) => onChange({ mode: 'existing', partner })}
          />
          <span className={HINT_CLASS}>
            {choice.suggested && choice.partner
              ? 'Bereits vorhanden — wird wiederverwendet, kein neuer Partner.'
              : 'Buchungen und Matcher landen beim gewählten Partner.'}
          </span>
        </>
      )}
    </div>
  )
}

function ServiceField({
  groupKey,
  mandantId,
  partnerId,
  serviceId,
  serviceName,
  onChange,
}: Readonly<{
  groupKey: string
  mandantId: string
  partnerId: string | null
  serviceId: string
  serviceName: string
  onChange: (next: { serviceId: string; serviceName: string }) => void
}>) {
  const { data: services = [] } = useQuery({
    queryKey: ['partner-services', mandantId, partnerId],
    queryFn: async () => {
      const all = await listPartnerServices(mandantId, partnerId as string)
      // Die Basisleistung ist kein Matcher-Ziel: Partnererkennung und
      // Leistungszuordnung ueberspringen sie beide, der Matcher waere tot.
      return all.filter((service) => !service.is_base_service)
    },
    enabled: !!mandantId && !!partnerId,
  })

  if (services.length === 0) {
    return (
      <label className="block">
        <span className={LABEL_CLASS}>Leistung</span>
        <input
          value={serviceName}
          aria-label={`Leistung für ${groupKey}`}
          onChange={(event) => onChange({ serviceId: '', serviceName: event.target.value })}
          className={FIELD_CLASS}
        />
        <span className={HINT_CLASS}>Art und Steuersatz werden automatisch erkannt.</span>
      </label>
    )
  }

  return (
    <div>
      <span className={LABEL_CLASS}>Leistung</span>
      <select
        value={serviceId}
        aria-label={`Leistung für ${groupKey}`}
        onChange={(event) => onChange({ serviceId: event.target.value, serviceName })}
        className={FIELD_CLASS}
      >
        <option value="">Neue Leistung anlegen …</option>
        {services.map((service) => (
          <option key={service.id} value={service.id}>
            {service.name}
          </option>
        ))}
      </select>
      {serviceId === '' && (
        <input
          value={serviceName}
          aria-label={`Name der neuen Leistung für ${groupKey}`}
          onChange={(event) => onChange({ serviceId: '', serviceName: event.target.value })}
          className={FIELD_CLASS}
        />
      )}
      <span className={HINT_CLASS}>
        {serviceId === ''
          ? 'Art und Steuersatz werden automatisch erkannt.'
          : 'Der Matcher wird an diese bestehende Leistung gehängt.'}
      </span>
    </div>
  )
}

function LineTable({ lines }: Readonly<{ lines: UnidentifiedGroupLine[] }>) {
  return (
    <div className="mt-2 max-h-64 overflow-y-auto rounded-lg bg-slate-50">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-slate-100 text-slate-500">
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-medium">
              Valuta
            </th>
            <th scope="col" className="px-2 py-1 text-left font-medium">
              Buchungstext
            </th>
            <th scope="col" className="px-2 py-1 text-right font-medium">
              Betrag
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id} className="border-t border-slate-200/70 align-top">
              <td className="whitespace-nowrap px-2 py-1 tabular-nums text-slate-500">
                {formatDate(line.valuta_date)}
              </td>
              <td className="break-all px-2 py-1 font-mono text-slate-600">{line.text ?? '—'}</td>
              <td
                className={`whitespace-nowrap px-2 py-1 text-right tabular-nums ${
                  Number.parseFloat(line.amount) < 0 ? 'text-rose-600' : 'text-emerald-600'
                }`}
              >
                {formatMoney(line.amount)} €
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function selectedPartnerId(choice: PartnerChoice): string | null {
  return choice.mode === 'existing' ? (choice.partner?.id ?? null) : null
}

function isPartnerReady(choice: PartnerChoice): boolean {
  return choice.mode === 'new' ? choice.name.trim().length > 0 : choice.partner !== null
}

function buildPayload(group: UnidentifiedGroup, form: GroupFormState): ResolveGroupRequest {
  const partner: Pick<ResolveGroupRequest, 'partner_id' | 'partner_name'> =
    form.partner.mode === 'existing' && form.partner.partner
      ? { partner_id: form.partner.partner.id }
      : { partner_name: form.partner.mode === 'new' ? form.partner.name.trim() : '' }
  const service: Pick<ResolveGroupRequest, 'service_id' | 'service_name'> = form.serviceId
    ? { service_id: form.serviceId }
    : { service_name: form.serviceName.trim() }
  return {
    item_ids: group.item_ids,
    pattern: form.pattern.trim(),
    ...service,
    ...partner,
  }
}

function GroupCard({
  group,
  onResolved,
  onError,
}: Readonly<{
  group: UnidentifiedGroup
  onResolved: (message: string) => void
  onError: (message: string) => void
}>) {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [form, setForm] = useState<GroupFormState>({
    // Kennt der Server den Haendler schon als Partner, startet die Karte bei
    // ihm - "neu anlegen" wuerde sonst ein Duplikat erzeugen, das sich nur in
    // Schreibweise oder Satzzeichen unterscheidet.
    partner: group.suggested_partner_id
      ? {
          mode: 'existing',
          partner: { id: group.suggested_partner_id, name: group.suggested_partner_name },
          suggested: true,
        }
      : { mode: 'new', name: group.suggested_partner_name },
    serviceId: '',
    serviceName: group.suggested_partner_name,
    pattern: group.suggested_pattern,
  })

  const mutation = useMutation({
    mutationFn: () => resolveUnidentifiedGroup(mandantId, buildPayload(group, form)),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['review'] })
      await queryClient.invalidateQueries({ queryKey: ['unidentified-groups'] })
      await queryClient.invalidateQueries({ queryKey: ['partners'] })
      onResolved(
        `${result.partner_name}: ${result.assigned_lines} Buchung(en) zugeordnet, Matcher „${form.pattern.trim()}" angelegt.`,
      )
    },
    onError: (error) =>
      onError(extractErrorMessage(error, 'Gruppe konnte nicht aufgelöst werden.')),
  })

  const canSubmit =
    isPartnerReady(form.partner) &&
    (form.serviceId !== '' || form.serviceName.trim().length > 0) &&
    form.pattern.trim().length >= 2 &&
    !mutation.isPending

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono text-sm font-semibold text-slate-900">{group.key}</h3>
        <div className="text-xs text-slate-500">
          {group.line_count} Buchung{group.line_count === 1 ? '' : 'en'}
          {' · '}
          <span
            className={
              Number.parseFloat(group.total_amount) < 0 ? 'text-rose-600' : 'text-emerald-600'
            }
          >
            {formatMoney(group.total_amount)} €
          </span>
          {' · '}
          {formatDate(group.first_date)} – {formatDate(group.last_date)}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="mt-1 text-xs text-slate-500 hover:text-slate-700 hover:underline"
      >
        {expanded ? 'Buchungen ausblenden' : `${group.line_count} Buchung(en) anzeigen`}
      </button>
      {expanded && <LineTable lines={group.lines} />}

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <PartnerField
          groupKey={group.key}
          mandantId={mandantId}
          choice={form.partner}
          onChange={(partner) =>
            // Die Leistungen gehören zum Partner - bei einem Wechsel ist die
            // bisherige Auswahl hinfällig.
            setForm((prev) => ({ ...prev, partner, serviceId: '' }))
          }
        />
        <ServiceField
          groupKey={group.key}
          mandantId={mandantId}
          partnerId={selectedPartnerId(form.partner)}
          serviceId={form.serviceId}
          serviceName={form.serviceName}
          onChange={(next) => setForm((prev) => ({ ...prev, ...next }))}
        />
        <label className="block">
          <span className={LABEL_CLASS}>Matcher-Muster</span>
          <input
            value={form.pattern}
            aria-label={`Matcher-Muster für ${group.key}`}
            onChange={(event) => setForm((prev) => ({ ...prev, pattern: event.target.value }))}
            className={FIELD_CLASS}
          />
          <span className={HINT_CLASS}>Trifft künftige Buchungen, die diesen Text enthalten.</span>
        </label>
      </div>

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={!canSubmit}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {mutation.isPending
            ? 'Wird angelegt …'
            : `Anlegen & ${group.line_count} Buchung(en) zuordnen`}
        </button>
      </div>
    </div>
  )
}

export function UnidentifiedGroupsPanel({
  onNotice,
}: Readonly<{ onNotice: (tone: 'success' | 'error', message: string) => void }>) {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const [collapsed, setCollapsed] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['unidentified-groups', mandantId],
    queryFn: () => listUnidentifiedGroups(mandantId),
    enabled: !!mandantId,
  })

  if (isLoading || !data || data.groups.length === 0) {
    return null
  }

  return (
    <section className="mb-6 rounded-2xl border border-amber-200 bg-amber-50/50 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-slate-900">Nach Händler zusammengefasst</h2>
        <button
          type="button"
          onClick={() => setCollapsed((prev) => !prev)}
          className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-white"
        >
          {collapsed ? 'Einblenden' : 'Ausblenden'}
        </button>
      </div>
      <p className="mt-1 text-sm text-slate-600">
        {data.grouped} von {data.total_open} offenen Buchungen ohne Partner verteilen sich auf{' '}
        <strong>{data.groups.length} Händler</strong>. Pro Gruppe legst du Partner, Leistung und
        Matcher in einem Schritt an — der Matcher greift danach auch bei künftigen Importen.
      </p>

      {!collapsed && (
        <div className="mt-4 space-y-3">
          {data.groups.map((group) => (
            <GroupCard
              key={group.key}
              group={group}
              onResolved={(message) => onNotice('success', message)}
              onError={(message) => onNotice('error', message)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

export default UnidentifiedGroupsPanel
