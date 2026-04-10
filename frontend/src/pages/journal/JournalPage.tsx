import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { listJournalLines, bulkAssignPartner } from '@/api/journal'
import type { JournalLine } from '@/api/journal'
import { listAccounts } from '@/api/accounts'
import { listPartners } from '@/api/partners'
import type { PartnerListItem } from '@/api/partners'

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - i)
const MONTHS = [
  { value: 1, label: 'Jan' }, { value: 2, label: 'Feb' }, { value: 3, label: 'Mär' },
  { value: 4, label: 'Apr' }, { value: 5, label: 'Mai' }, { value: 6, label: 'Jun' },
  { value: 7, label: 'Jul' }, { value: 8, label: 'Aug' }, { value: 9, label: 'Sep' },
  { value: 10, label: 'Okt' }, { value: 11, label: 'Nov' }, { value: 12, label: 'Dez' },
]

export function JournalPage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const role = useAuthStore((s) => s.user?.role ?? '')
  const queryClient = useQueryClient()

  // Filters
  const [year, setYear] = useState<number | undefined>(CURRENT_YEAR)
  const [month, setMonth] = useState<number | undefined>(undefined)
  const [accountId, setAccountId] = useState<string>('')
  const [hasPartner, setHasPartner] = useState<'all' | 'yes' | 'no'>('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // Sorting
  const [sortBy, setSortBy] = useState<string>('valuta_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  function handleSort(col: string) {
    if (sortBy === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      setSortDir('asc')
    }
    setPage(1)
  }

  function SortIcon({ col }: { col: string }) {
    if (sortBy !== col) return <span className="ml-1 opacity-30">⇅</span>
    return <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  // Bulk-assign
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkPartnerQuery, setBulkPartnerQuery] = useState('')
  const [bulkPartnerResults, setBulkPartnerResults] = useState<PartnerListItem[]>([])
  const [showBulkDialog, setShowBulkDialog] = useState(false)

  // Info-Tooltip
  const [tooltip, setTooltip] = useState<{ line: JournalLine; top: number; right: number } | null>(null)
  const handleTooltipEnter = (e: React.MouseEvent, line: JournalLine) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const tooltipHeight = 380
    const top = rect.bottom + 8 + tooltipHeight > window.innerHeight
      ? rect.top - tooltipHeight - 4
      : rect.bottom + 4
    setTooltip({ line, top, right: window.innerWidth - rect.right })
  }


  const canBulkAssign = role === 'accountant' || role === 'mandant_admin' || role === 'admin'

  const filter = {
    ...(year ? { year } : {}),
    ...(month ? { month } : {}),
    ...(accountId ? { account_id: accountId } : {}),
    ...(hasPartner === 'yes' ? { has_partner: true } : hasPartner === 'no' ? { has_partner: false } : {}),
    ...(search.trim() ? { search: search.trim() } : {}),
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    size: 50,
  }

  const { data, isLoading } = useQuery({
    queryKey: ['journal', mandantId, filter],
    queryFn: () => listJournalLines(mandantId, filter),
    enabled: !!mandantId,
  })

  const { data: accounts } = useQuery({
    queryKey: ['accounts', mandantId],
    queryFn: () => listAccounts(mandantId),
    enabled: !!mandantId,
  })

  const bulkMutation = useMutation({
    mutationFn: (partnerId: string) =>
      bulkAssignPartner(mandantId, Array.from(selected), partnerId),
    onSuccess: () => {
      setSelected(new Set())
      setShowBulkDialog(false)
      setBulkPartnerQuery('')
      queryClient.invalidateQueries({ queryKey: ['journal', mandantId] })
    },
  })

  function toggleAll(lines: JournalLine[]) {
    if (selected.size === lines.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(lines.map((l) => l.id)))
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function searchBulkPartner(q: string) {
    setBulkPartnerQuery(q)
    if (q.length < 2) {
      setBulkPartnerResults([])
      return
    }
    const res = await listPartners(mandantId, 1, 10)
    setBulkPartnerResults(
      res.items.filter(
        (p) => p.is_active && p.name.toLowerCase().includes(q.toLowerCase()),
      ),
    )
  }

  const lines = data?.items ?? []

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Buchungsjournal</h1>

      {/* Filter Bar */}
      <div className="mb-4 flex flex-wrap gap-3">
        <select
          value={year ?? ''}
          onChange={(e) => { setYear(e.target.value ? Number(e.target.value) : undefined); setPage(1) }}
          className="rounded border px-3 py-1.5 text-sm"
        >
          <option value="">Alle Jahre</option>
          {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>

        <select
          value={month ?? ''}
          onChange={(e) => { setMonth(e.target.value ? Number(e.target.value) : undefined); setPage(1) }}
          className="rounded border px-3 py-1.5 text-sm"
        >
          <option value="">Alle Monate</option>
          {MONTHS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>

        <select
          value={accountId}
          onChange={(e) => { setAccountId(e.target.value); setPage(1) }}
          className="rounded border px-3 py-1.5 text-sm"
        >
          <option value="">Alle Konten</option>
          {(accounts ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>

        <select
          value={hasPartner}
          onChange={(e) => { setHasPartner(e.target.value as 'all' | 'yes' | 'no'); setPage(1) }}
          className="rounded border px-3 py-1.5 text-sm"
        >
          <option value="all">Mit & ohne Partner</option>
          <option value="yes">Nur mit Partner</option>
          <option value="no">Ohne Partner</option>
        </select>
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          placeholder="Text oder Partnername…"
          className="rounded border px-3 py-1.5 text-sm min-w-48 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        {data && data.pages > 1 && (
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
            >
              ← Zurück
            </button>
            <span className="px-2 text-sm text-gray-500">{page} / {data.pages} ({data.total} Zeilen)</span>
            <button
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={page === data.pages}
              className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
            >
              Weiter →
            </button>
          </div>
        )}
      </div>
      {canBulkAssign && selected.size > 0 && (
        <div className="mb-3 flex items-center gap-3 rounded-lg bg-blue-50 px-4 py-2">
          <span className="text-sm font-medium text-blue-700">
            {selected.size} Zeile(n) ausgewählt
          </span>
          <button
            onClick={() => setShowBulkDialog(true)}
            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
          >
            Partner zuweisen
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="text-xs text-blue-500 hover:underline"
          >
            Auswahl aufheben
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
            <tr>
              {canBulkAssign && (
                <th className="w-8 px-3 py-3">
                  <input
                    type="checkbox"
                    checked={lines.length > 0 && selected.size === lines.length}
                    onChange={() => toggleAll(lines)}
                    className="rounded"
                  />
                </th>
              )}
              <th
                className="cursor-pointer select-none whitespace-nowrap px-3 py-3 text-left hover:text-gray-700"
                onClick={() => handleSort('valuta_date')}
              >
                Valuta<SortIcon col="valuta_date" />
              </th>
              <th
                className="cursor-pointer select-none px-3 py-3 text-left hover:text-gray-700"
                onClick={() => handleSort('booking_date')}
              >
                Buchung<SortIcon col="booking_date" />
              </th>
              <th
                className="cursor-pointer select-none px-3 py-3 text-left hover:text-gray-700"
                onClick={() => handleSort('text')}
              >
                Text<SortIcon col="text" />
              </th>
              <th
                className="cursor-pointer select-none px-3 py-3 text-left hover:text-gray-700"
                onClick={() => handleSort('partner_name')}
              >
                Partner<SortIcon col="partner_name" />
              </th>
              <th
                className="cursor-pointer select-none px-3 py-3 text-right hover:text-gray-700"
                onClick={() => handleSort('amount')}
              >
                Betrag<SortIcon col="amount" />
              </th>
              <th className="w-8 px-3 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={canBulkAssign ? 7 : 6} className="px-3 py-8 text-center">
                  <div className="inline-block h-6 w-6 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
                </td>
              </tr>
            )}
            {!isLoading && lines.length === 0 && (
              <tr>
                <td colSpan={canBulkAssign ? 7 : 6} className="px-3 py-8 text-center text-gray-400">
                  Keine Buchungszeilen für diesen Filter.
                </td>
              </tr>
            )}
            {lines.map((line) => (
              <React.Fragment key={line.id}>
              <tr
                className={`hover:bg-gray-50 ${selected.has(line.id) ? 'bg-blue-50' : ''}`}
              >
                {canBulkAssign && (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(line.id)}
                      onChange={() => toggleOne(line.id)}
                      className="rounded"
                    />
                  </td>
                )}
                <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-500">{line.valuta_date}</td>
                <td className="px-3 py-2 font-mono text-xs text-gray-400">{line.booking_date}</td>
                <td className="max-w-xs truncate px-3 py-2 text-gray-700">
                  {line.text ?? line.partner_name_raw ?? <em className="text-gray-400">—</em>}
                </td>
                <td className="px-3 py-2">
                  {line.partner_id ? (
                    <Link
                      to={`/partners/${line.partner_id}`}
                      className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 hover:bg-green-200 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {line.partner_name ?? line.partner_name_raw ?? line.partner_id.substring(0, 8) + '…'}
                    </Link>
                  ) : (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                </td>
                <td className={`px-3 py-2 text-right font-mono text-sm ${Number(line.amount) < 0 ? 'text-red-600' : 'text-green-700'}`}>
                  {Number(line.amount).toLocaleString('de-DE', { style: 'currency', currency: line.currency })}
                </td>
                <td className="px-3 py-2 text-center">
                  <div
                    className="inline-block"
                    onMouseEnter={(e) => handleTooltipEnter(e, line)}
                    onMouseLeave={() => setTooltip(null)}
                  >
                    <button
                      onClick={(e) => e.stopPropagation()}
                      className="rounded p-0.5 text-gray-400 hover:text-blue-600"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Bulk-Assign Dialog */}
      {showBulkDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <h2 className="mb-3 text-base font-semibold">Partner zuweisen</h2>
            <p className="mb-3 text-sm text-gray-500">
              Für {selected.size} ausgewählte Buchungszeile(n).
            </p>
            <div className="relative">
              <input
                value={bulkPartnerQuery}
                onChange={(e) => searchBulkPartner(e.target.value)}
                placeholder="Partner suchen…"
                className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {bulkPartnerResults.length > 0 && (
                <ul className="absolute z-10 mt-1 w-full divide-y divide-gray-100 rounded border border-gray-200 bg-white shadow-md">
                  {bulkPartnerResults.map((p) => (
                    <li
                      key={p.id}
                      onClick={() => bulkMutation.mutate(p.id)}
                      className="cursor-pointer px-3 py-2 text-sm hover:bg-blue-50"
                    >
                      {p.name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {bulkMutation.isError && (
              <p className="mt-2 text-xs text-red-500">Fehler beim Zuweisen.</p>
            )}
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => { setShowBulkDialog(false); setBulkPartnerQuery('') }}
                className="rounded px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100"
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Info-Tooltip (fixed, außerhalb Scroll-Container) */}
      {tooltip && (
        <div
          className="pointer-events-none fixed z-50 w-[520px] rounded-lg border border-gray-200 bg-white p-3 shadow-xl"
          style={{ top: tooltip.top, right: tooltip.right }}
        >
          <table className="w-full text-xs">
            <tbody>
              {([
                ['ID', tooltip.line.id],
                ['Konto-ID', tooltip.line.account_id],
                ['Import-Run', tooltip.line.import_run_id],
                ['Valutadatum', tooltip.line.valuta_date],
                ['Buchungsdatum', tooltip.line.booking_date],
                ['Währung', tooltip.line.currency],
                ['Buchungstext', tooltip.line.text],
                ['Partner (roh)', tooltip.line.partner_name_raw],
                ['IBAN (roh)', tooltip.line.partner_iban_raw],
                ['Kontonummer (roh)', tooltip.line.partner_account_raw],
                ['BLZ (roh)', tooltip.line.partner_blz_raw],
                ['BIC (roh)', tooltip.line.partner_bic_raw],
                ['Partner-ID', tooltip.line.partner_id],
                ['Erstellt', new Date(tooltip.line.created_at + 'Z').toLocaleString('de-DE', { timeZone: 'Europe/Vienna' })],
                ...(tooltip.line.unmapped_data ? Object.entries(tooltip.line.unmapped_data).map(([k, v]) => [k, v] as [string, string]) : []),
              ] as [string, string | null | undefined][]).filter(([, v]) => v).map(([label, value]) => (
                <tr key={label}>
                  <td className="py-0.5 pr-3 align-top font-semibold text-gray-500 whitespace-nowrap text-right">{label}</td>
                  <td className="py-0.5 break-all font-mono text-gray-700 text-left">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
