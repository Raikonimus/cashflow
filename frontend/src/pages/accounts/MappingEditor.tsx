import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { getMapping, saveMapping, previewCsvColumns } from '@/api/accounts'
import type { ColumnAssignment } from '@/api/accounts'

// ─── Zielfeld-Optionen ────────────────────────────────────────────────────────

const TARGET_OPTIONS: { value: string; label: string }[] = [
  { value: 'valuta_date',    label: 'Valutadatum *' },
  { value: 'booking_date',  label: 'Buchungsdatum *' },
  { value: 'amount',        label: 'Betrag *' },
  { value: 'currency',      label: 'Währung' },
  { value: 'partner_iban',  label: 'Partner-IBAN' },
  { value: 'partner_account', label: 'Partner-Kontonummer' },
  { value: 'partner_blz',   label: 'Partner-BLZ' },
  { value: 'partner_bic',   label: 'Partner-BIC/SWIFT' },
  { value: 'partner_name',  label: 'Partnername' },
  { value: 'description',   label: 'Verwendungszweck' },
  { value: 'unused',        label: '— Nicht verwendet —' },
]

// Suchbegriffe pro Zielfeld (Deutsch + Englisch, lowercase)
const TARGET_KEYWORDS: Record<string, string[]> = {
  valuta_date:     ['valuta'],
  booking_date:    ['buchung', 'booking'],
  amount:          ['betrag', 'amount', 'summe', 'saldo', 'umsatz'],
  currency:        ['währung', 'currency', 'devisen', 'waehrung'],
  partner_iban:    ['iban'],
  partner_account: ['kontonummer', 'konto', 'account', 'accountnumber'],
  partner_blz:     ['blz', 'bankleitzahl', 'bankcode'],
  partner_bic:     ['bic', 'swift'],
  partner_name:    ['partner', 'name', 'auftraggeber', 'empfänger', 'beguenstigter'],
  description:     ['verwendung', 'zweck', 'detail', 'text', 'beschreibung', 'memo', 'info', 'buchungsdetail'],
}

/** Gibt das passende Zielfeld zurück, wenn der Spaltenname einem Keyword entspricht oder es enthält. */
function autoSuggestTarget(colName: string): string {
  const col = colName.toLowerCase().replaceAll(/[^a-z0-9äöüß]/g, '')
  for (const [target, keywords] of Object.entries(TARGET_KEYWORDS)) {
    for (const kw of keywords) {
      const kwNorm = kw.replaceAll(/[^a-z0-9äöüß]/g, '')
      if (col.includes(kwNorm) || kwNorm.includes(col)) return target
    }
  }
  return ''
}

// ─── Typen ────────────────────────────────────────────────────────────────────

interface LegacyFields {
  valuta_date_col: string
  booking_date_col: string
  amount_col: string
  partner_name_col: string
  partner_iban_col: string
  description_col: string
}

interface ParserConfig {
  delimiter: string
  decimal_separator: string
  date_format: string
  encoding: string
  skip_rows: number
}

interface MappingEditorProps {
  accountId: string
  onSaved?: () => void
}

// ─── Komponente ───────────────────────────────────────────────────────────────

export function MappingEditor({ accountId, onSaved }: Readonly<MappingEditorProps>) {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const queryClient = useQueryClient()

  // Parser-Konfiguration (immer sichtbar)
  const [parser, setParser] = useState<ParserConfig>({
    delimiter: ';',
    decimal_separator: ',',
    date_format: '%d.%m.%Y',
    encoding: 'cp1252',
    skip_rows: 0,
  })

  // Assignment-Modus: erkannte CSV-Spalten + ihre Zuordnung
  const [csvColumns, setCsvColumns] = useState<string[] | null>(null)
  const [assignments, setAssignments] = useState<Record<string, string>>({})
  const [duplicateChecks, setDuplicateChecks] = useState<Record<string, boolean>>({})
  const [sampleRows, setSampleRows] = useState<Record<string, string>[]>([])
  const [previewRowIdx, setPreviewRowIdx] = useState(0)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // Legacy-Modus (manuelle Texteingabe, rückwärtskompatibel)
  const [legacy, setLegacy] = useState<LegacyFields>({
    valuta_date_col: '',
    booking_date_col: '',
    amount_col: '',
    partner_name_col: '',
    partner_iban_col: '',
    description_col: '',
  })

  // Mapping aus API laden
  const { data: mapping, isLoading } = useQuery({
    queryKey: ['mapping', mandantId, accountId],
    queryFn: () => getMapping(mandantId, accountId),
  })

  // Einmalig aus geladenen Daten initialisieren
  const initializedRef = useRef(false)
  useEffect(() => {
    if (!mapping || initializedRef.current) return
    initializedRef.current = true

    setParser({
      delimiter: mapping.delimiter,
      decimal_separator: mapping.decimal_separator,
      date_format: mapping.date_format,
      encoding: mapping.encoding,
      skip_rows: mapping.skip_rows,
    })

    if (mapping.column_assignments && mapping.column_assignments.length > 0) {
      const sorted = [...mapping.column_assignments].sort((a, b) => a.sort_order - b.sort_order)
      const cols = [...new Set(sorted.map((a) => a.source))]
      const assn: Record<string, string> = {}
      const duplicateFlags: Record<string, boolean> = {}
      for (const a of sorted) assn[a.source] = a.target
      for (const a of sorted) duplicateFlags[a.source] = a.duplicate_check ?? false
      setCsvColumns(cols)
      setAssignments(assn)
      setDuplicateChecks(duplicateFlags)
    } else {
      setLegacy({
        valuta_date_col: mapping.valuta_date_col ?? '',
        booking_date_col: mapping.booking_date_col ?? '',
        amount_col: mapping.amount_col ?? '',
        partner_name_col: mapping.partner_name_col ?? '',
        partner_iban_col: mapping.partner_iban_col ?? '',
        description_col: mapping.description_col ?? '',
      })
    }
  }, [mapping])

  // CSV-Datei hochladen → Spalten erkennen
  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const result = await previewCsvColumns(
        mandantId, accountId, file,
        parser.delimiter, parser.encoding, parser.skip_rows,
      )
      if (result.columns.length === 0) {
        setPreviewError('Keine Spalten erkannt – Trennzeichen und Zeichensatz prüfen.')
        return
      }
      // Erkanntes Trennzeichen + Zeichensatz in Parser-State übernehmen
      setParser((p) => ({
        ...p,
        ...(result.detected_delimiter ? { delimiter: result.detected_delimiter } : {}),
        ...(result.detected_encoding  ? { encoding:  result.detected_encoding  } : {}),
      }))
      const cols = result.columns
      // Bestehende Zuordnungen erhalten; neue Spalten auto-vorschlagen oder leer
      const newAssn: Record<string, string> = {}
      const newDuplicateChecks: Record<string, boolean> = {}
      for (const col of cols) newAssn[col] = assignments[col] || autoSuggestTarget(col)
      for (const col of cols) newDuplicateChecks[col] = duplicateChecks[col] ?? false
      setCsvColumns(cols)
      setAssignments(newAssn)
      setDuplicateChecks(newDuplicateChecks)
      setSampleRows(result.sample_rows ?? [])
      setPreviewRowIdx(0)
    } catch {
      setPreviewError('CSV konnte nicht analysiert werden. Einstellungen prüfen.')
    } finally {
      setPreviewLoading(false)
      e.target.value = ''
    }
  }

  // Speichern
  const mutation = useMutation({
    mutationFn: () => {
      if (csvColumns !== null) {
        const column_assignments: ColumnAssignment[] = csvColumns.map((col, i) => ({
          source: col,
          target: assignments[col] || 'unused',
          sort_order: i,
          duplicate_check: duplicateChecks[col] ?? false,
        }))
        return saveMapping(mandantId, accountId, { column_assignments, ...parser })
      }
      // Legacy-Modus
      return saveMapping(mandantId, accountId, {
        ...legacy,
        partner_name_col: legacy.partner_name_col || null,
        partner_iban_col: legacy.partner_iban_col || null,
        description_col: legacy.description_col || null,
        ...parser,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mapping', mandantId, accountId] })
      onSaved?.()
    },
  })

  // Validierung
  const isAssignmentMode = csvColumns === null
  const canSave = isAssignmentMode
    ? !!legacy.valuta_date_col && !!legacy.booking_date_col && !!legacy.amount_col
    : csvColumns.length > 0
      && csvColumns.every((col) => !!assignments[col])
      && csvColumns.some((col) => duplicateChecks[col])

  const unassignedCount = isAssignmentMode
    ? 0
    : csvColumns.filter((col) => !assignments[col]).length
  const duplicateCheckCount = isAssignmentMode
    ? 0
    : csvColumns.filter((col) => duplicateChecks[col]).length

  if (isLoading) {
    return <div className="text-sm text-gray-400">Lade Mapping-Konfiguration …</div>
  }

  return (
    <div className="space-y-5">

      {/* ── Parser-Einstellungen ─────────────────────────────────────────── */}
      <section className="rounded-xl border border-gray-200 bg-gray-50 p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">CSV-Parser-Einstellungen</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {([
            { key: 'delimiter',         label: 'Trennzeichen',           placeholder: ';' },
            { key: 'decimal_separator', label: 'Dezimaltrennzeichen',    placeholder: ',' },
            { key: 'date_format',       label: 'Datumsformat',           placeholder: '%d.%m.%Y' },
          ] as { key: keyof ParserConfig; label: string; placeholder: string }[]).map(({ key, label, placeholder }) => (
            <label key={key} className="block">
              <span className="text-xs font-medium text-gray-600">{label}</span>
              <input
                value={String(parser[key])}
                onChange={(e) => setParser((p) => ({ ...p, [key]: e.target.value }))}
                placeholder={placeholder}
                className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </label>
          ))}
          <label className="block">
            <span className="text-xs font-medium text-gray-600">Zeichensatz</span>
            <select
              value={parser.encoding}
              onChange={(e) => setParser((p) => ({ ...p, encoding: e.target.value }))}
              className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="utf-16">utf-16 (Raiffeisen/ELBA, UTF-16 BOM)</option>
              <option value="cp1252">cp1252 (Windows, dt. Banken)</option>
              <option value="utf-8">utf-8</option>
              <option value="utf-8-sig">utf-8-sig (Excel UTF-8 mit BOM)</option>
              <option value="latin-1">latin-1 (ISO-8859-1)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-600">Kopfzeilen überspringen</span>
            <input
              type="number"
              value={parser.skip_rows}
              min={0}
              onChange={(e) => setParser((p) => ({ ...p, skip_rows: Number(e.target.value) }))}
              className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
        </div>
      </section>

      {/* ── CSV hochladen → Spalten erkennen ────────────────────────────── */}
      <section className="rounded-xl border border-gray-200 p-4">
        <h3 className="mb-1 text-sm font-semibold text-gray-700">CSV hochladen zur Spalten-Erkennung</h3>
        <p className="mb-3 text-xs text-gray-500">
          Wähle eine CSV-Datei, um die Spaltennamen automatisch zu erkennen.
          Die Parser-Einstellungen oben werden dabei berücksichtigt.
          Mehrere Spalten können demselben Zielfeld zugewiesen werden – der Inhalt wird dann mit Zeilenumbruch zusammengeführt.
        </p>
        <label className={`flex cursor-pointer items-center gap-2 rounded-lg border-2 border-dashed px-4 py-3 text-sm transition-colors ${
          previewLoading
            ? 'border-blue-300 bg-blue-50 text-blue-500'
            : 'border-gray-300 bg-gray-50 text-gray-600 hover:border-blue-400 hover:bg-blue-50'
        }`}>
          {previewLoading ? 'Analysiere CSV …' : 'CSV-Datei auswählen …'}
          <input
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileChange}
            disabled={previewLoading}
          />
        </label>
        {previewError && <p className="mt-2 text-xs text-red-500">{previewError}</p>}
      </section>

      {/* ── Spaltenzuordnung (Dropdown-Tabelle) ─────────────────────────── */}
      {csvColumns !== null && (
        <section className="rounded-xl border border-gray-200 p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-700">
            Spaltenzuordnung
            {' '}
            <span className="ml-2 text-xs font-normal text-gray-400">
              {csvColumns.length} Spalten erkannt · * Pflichtfeld
              {unassignedCount > 0 && (
                <span className="ml-2 font-medium text-amber-600">
                  {unassignedCount} noch nicht zugeordnet
                </span>
              )}
              {duplicateCheckCount === 0 && (
                <span className="ml-2 font-medium text-amber-600">
                  keine Dubletten-Spalte ausgewählt
                </span>
              )}
            </span>
          </h3>
          {sampleRows.length > 0 && (
            <div className="mb-3 flex items-center gap-2">
              <span className="text-xs text-gray-500">Beispielzeile:</span>
              <button
                onClick={() => setPreviewRowIdx((i) => Math.max(0, i - 1))}
                disabled={previewRowIdx === 0}
                className="rounded border border-gray-200 px-2 py-0.5 text-xs hover:bg-gray-100 disabled:opacity-40"
              >← Vorherige</button>
              <span className="text-xs font-medium text-gray-600">
                Zeile {previewRowIdx + 1} von {sampleRows.length}
              </span>
              <button
                onClick={() => setPreviewRowIdx((i) => Math.min(sampleRows.length - 1, i + 1))}
                disabled={previewRowIdx === sampleRows.length - 1}
                className="rounded border border-gray-200 px-2 py-0.5 text-xs hover:bg-gray-100 disabled:opacity-40"
              >Nächste →</button>
            </div>
          )}
          <div className="overflow-hidden rounded-lg border border-gray-100">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">CSV-Spalte</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Beispielwert</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Dublettenprüfung</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Zielfeld</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {csvColumns.map((col) => {
                  const val = assignments[col] ?? ''
                  const missing = !val
                  const sampleVal = sampleRows[previewRowIdx]?.[col] ?? ''
                  const isTruncated = sampleVal.length > 40
                  return (
                    <tr key={col} className={missing ? 'bg-amber-50' : undefined}>
                      <td className="px-3 py-2 font-mono text-gray-700">{col}</td>
                      <td className="px-3 py-2 text-gray-500 text-xs">
                        <span
                          className="relative group inline-block max-w-[200px] truncate align-bottom cursor-default"
                          title={isTruncated ? sampleVal : undefined}
                        >
                          {sampleVal || <span className="italic text-gray-300">leer</span>}
                          {isTruncated && (
                            <span className="pointer-events-none absolute left-0 top-full z-50 mt-1 hidden w-max max-w-xs rounded bg-gray-900 px-2 py-1 text-xs text-white shadow-lg group-hover:block whitespace-pre-wrap break-all">
                              {sampleVal}
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <label className="inline-flex items-center gap-2 text-xs text-gray-600">
                          <input
                            type="checkbox"
                            checked={duplicateChecks[col] ?? false}
                            onChange={(e) => setDuplicateChecks((current) => ({
                              ...current,
                              [col]: e.target.checked,
                            }))}
                            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          {' '}
                          verwenden
                        </label>
                      </td>
                      <td className="px-3 py-2">
                        <select
                          value={val}
                          onChange={(e) => setAssignments((a) => ({ ...a, [col]: e.target.value }))}
                          className={`w-full rounded border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                            missing ? 'border-amber-400' : 'border-gray-200'
                          }`}
                        >
                          <option value="">— Bitte auswählen —</option>
                          {TARGET_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {!canSave && (
            <p className="mt-2 text-xs text-amber-600">
              Bitte jeder Spalte ein Zielfeld zuweisen oder „Nicht verwendet" wählen und mindestens eine Dubletten-Spalte markieren.
            </p>
          )}
        </section>
      )}

      {/* ── Legacy-Modus: manuelle Texteingabe ──────────────────────────── */}
      {csvColumns === null && (
        <section className="rounded-xl border border-gray-200 p-4">
          <h3 className="mb-1 text-sm font-semibold text-gray-700">Spaltennamen (manuell)</h3>
          <p className="mb-3 text-xs text-gray-500">
            Alternativ kannst du die Spaltennamen direkt eingeben.
            Empfehlung: CSV oben hochladen für geführtes Mapping mit Dropdowns.
          </p>
          <div className="grid grid-cols-2 gap-3">
            {([
              { key: 'valuta_date_col',  label: 'Valutadatum *',            placeholder: 'Valuta' },
              { key: 'booking_date_col', label: 'Buchungsdatum *',           placeholder: 'Buchungsdatum' },
              { key: 'amount_col',       label: 'Betrag *',                  placeholder: 'Betrag' },
              { key: 'partner_name_col', label: 'Partnername (optional)',     placeholder: 'Auftraggeber' },
              { key: 'partner_iban_col', label: 'Partner-IBAN (optional)',    placeholder: 'IBAN' },
              { key: 'description_col',  label: 'Verwendungszweck (optional)', placeholder: 'Verwendungszweck' },
            ] as { key: keyof LegacyFields; label: string; placeholder: string }[]).map(({ key, label, placeholder }) => (
              <label key={key} className="block">
                <span className="text-xs font-medium text-gray-600">{label}</span>
                <input
                  value={legacy[key]}
                  onChange={(e) => setLegacy((v) => ({ ...v, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </label>
            ))}
          </div>
        </section>
      )}

      {/* ── Fehler / Erfolg / Speichern ──────────────────────────────────── */}
      {mutation.isError && (
        <p className="text-sm text-red-500">Fehler beim Speichern der Konfiguration.</p>
      )}
      {mutation.isSuccess && (
        <p className="text-sm text-green-600">✓ Konfiguration gespeichert.</p>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => mutation.mutate()}
          disabled={!canSave || mutation.isPending}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {mutation.isPending ? 'Speichern …' : 'Speichern'}
        </button>
      </div>

    </div>
  )
}
