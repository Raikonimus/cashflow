import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listUnidentifiedGroups, resolveUnidentifiedGroup } from '@/api/review'
import type { UnidentifiedGroup } from '@/api/review'
import { extractErrorMessage } from '@/api/errors'
import { useAuthStore } from '@/store/auth-store'

/**
 * Fasst offene "kein Partner erkannt"-Einträge nach Händler zusammen.
 *
 * Ein Kartenimport erzeugt hunderte Einzelfälle, die sich auf wenige
 * wiederkehrende Händler verteilen. Pro Gruppe legt ein Klick Partner,
 * Leistung und Matcher an und ordnet alle Zeilen zu — und der Matcher greift
 * danach auch bei künftigen Importen.
 */

function formatMoney(value: string): string {
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) {
    return value
  }
  return numeric.toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(value: string): string {
  const [year, month, day] = value.split('-')
  return day && month && year ? `${day}.${month}.${year}` : value
}

interface GroupFormState {
  partnerName: string
  serviceName: string
  pattern: string
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
    partnerName: group.suggested_partner_name,
    serviceName: group.suggested_partner_name,
    pattern: group.suggested_pattern,
  })

  const mutation = useMutation({
    mutationFn: () =>
      resolveUnidentifiedGroup(mandantId, {
        item_ids: group.item_ids,
        pattern: form.pattern.trim(),
        service_name: form.serviceName.trim(),
        partner_name: form.partnerName.trim(),
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['review'] })
      await queryClient.invalidateQueries({ queryKey: ['unidentified-groups'] })
      onResolved(
        `${result.partner_name}: ${result.assigned_lines} Buchung(en) zugeordnet, Matcher „${form.pattern.trim()}" angelegt.`,
      )
    },
    onError: (error) => onError(extractErrorMessage(error, 'Gruppe konnte nicht aufgelöst werden.')),
  })

  const canSubmit =
    form.partnerName.trim().length > 0 &&
    form.serviceName.trim().length > 0 &&
    form.pattern.trim().length >= 2 &&
    !mutation.isPending

  const fields: { key: keyof GroupFormState; label: string; hint: string }[] = [
    { key: 'partnerName', label: 'Partner', hint: 'Bestehender Partner mit exakt diesem Namen wird wiederverwendet.' },
    { key: 'serviceName', label: 'Leistung', hint: 'Art und Steuersatz werden automatisch erkannt.' },
    { key: 'pattern', label: 'Matcher-Muster', hint: 'Trifft künftige Buchungen, die diesen Text enthalten.' },
  ]

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono text-sm font-semibold text-slate-900">{group.key}</h3>
        <div className="text-xs text-slate-500">
          {group.line_count} Buchung{group.line_count === 1 ? '' : 'en'}
          {' · '}
          <span className={Number.parseFloat(group.total_amount) < 0 ? 'text-rose-600' : 'text-emerald-600'}>
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
        {expanded ? 'Beispieltexte ausblenden' : `${group.sample_texts.length} Beispieltext(e) anzeigen`}
      </button>
      {expanded && (
        <ul className="mt-2 space-y-1 rounded-lg bg-slate-50 p-2 font-mono text-xs text-slate-600">
          {group.sample_texts.map((text) => (
            <li key={text} className="break-all">{text}</li>
          ))}
        </ul>
      )}

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {fields.map(({ key, label, hint }) => (
          <label key={key} className="block">
            <span className="text-xs font-medium text-slate-600">{label}</span>
            <input
              value={form[key]}
              aria-label={`${label} für ${group.key}`}
              onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            />
            <span className="mt-1 block text-[11px] leading-4 text-slate-400">{hint}</span>
          </label>
        ))}
      </div>

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={!canSubmit}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {mutation.isPending ? 'Wird angelegt …' : `Anlegen & ${group.line_count} Buchung(en) zuordnen`}
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
        <strong>{data.groups.length} Händler</strong>. Pro Gruppe legst du Partner, Leistung und Matcher in einem
        Schritt an — der Matcher greift danach auch bei künftigen Importen.
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
