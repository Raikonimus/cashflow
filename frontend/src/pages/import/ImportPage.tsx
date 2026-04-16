import { useRef, useState } from 'react'
import axios from 'axios'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth-store'
import { uploadCsv, listImportRuns } from '@/api/imports'
import type { ImportRunDetail, ImportDuplicateInfo } from '@/api/imports'
import { listAccounts } from '@/api/accounts'

type Step = 'upload' | 'result'

function getUploadErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return 'Der Upload konnte nicht verarbeitet werden.'
  }

  if (!error.response) {
    return 'Der Server ist nicht erreichbar. Bitte prüfen Sie, ob Backend und API laufen.'
  }

  const responseData = error.response.data
  if (typeof responseData === 'string') {
    const plainMessage = responseData.trim()
    if (plainMessage && !plainMessage.startsWith('<')) {
      return plainMessage
    }
  }

  const detail = error.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') {
          return item
        }
        if (item && typeof item === 'object') {
          const msg = typeof item.msg === 'string' ? item.msg : ''
          const loc = Array.isArray(item.loc) ? item.loc.join(' -> ') : ''
          return [loc, msg].filter(Boolean).join(': ')
        }
        return ''
      })
      .filter(Boolean)

    if (messages.length > 0) {
      return messages.join(' | ')
    }
  }

  const statusText = error.response.statusText?.trim()
  if (statusText) {
    return `${error.response.status}: ${statusText}`
  }

  const message = error.message?.trim()
  if (message) {
    return message
  }

  return 'Der Upload konnte nicht verarbeitet werden.'
}

export function ImportPage() {
  const { accountId } = useParams<{ accountId: string }>()
  const resolvedAccountId = accountId ?? ''
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [step, setStep] = useState<Step>('upload')
  const [results, setResults] = useState<ImportRunDetail[]>([])
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts', mandantId],
    queryFn: () => listAccounts(mandantId),
    enabled: !!mandantId,
  })

  const { data: history } = useQuery({
    queryKey: ['import-runs', mandantId, accountId],
    queryFn: () => listImportRuns(mandantId, resolvedAccountId),
    enabled: !!mandantId && !!accountId,
  })

  const account = accounts.find((a) => a.id === accountId)

  const mutation = useMutation({
    mutationFn: () => uploadCsv(mandantId, resolvedAccountId, selectedFiles),
    onSuccess: (data) => {
      setResults(data)
      setStep('result')
      queryClient.invalidateQueries({ queryKey: ['import-runs', mandantId, accountId] })
      queryClient.invalidateQueries({ queryKey: ['review-badge'] })
    },
  })

  const uploadErrorMessage = mutation.isError
    ? getUploadErrorMessage(mutation.error)
    : null

  if (!accountId) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">
        Kein Konto ausgewählt.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-2 text-sm text-gray-400">
        <Link to="/accounts" className="hover:underline">Konten</Link>
        {account && (
          <>
            {' / '}
            <Link to={`/accounts/${accountId}`} className="hover:underline">{account.name}</Link>
          </>
        )}
        {' / Import'}
      </div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">CSV-Import</h1>

      {/* Step indicators */}
      <div className="mb-8 flex items-center gap-4">
        <StepBadge number={1} label="Dateien wählen" active={step === 'upload'} done={step === 'result'} />
        <div className="h-px flex-1 bg-gray-200" />
        <StepBadge number={2} label="Ergebnis" active={step === 'result'} done={false} />
      </div>

      {step === 'upload' && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <p className="mb-4 text-sm text-gray-600">
            Wählen Sie eine oder mehrere CSV-Dateien für das Konto{' '}
            <strong>{account?.name ?? accountId}</strong>.
          </p>

          <label className="mb-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-8 hover:border-blue-400">
            <svg className="mb-2 h-10 w-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm text-gray-500">
              {selectedFiles.length > 0
                ? `${selectedFiles.length} Datei(en) ausgewählt`
                : 'CSV-Dateien hierher ziehen oder klicken zum Auswählen'}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              multiple
              className="hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? [])
                setSelectedFiles(files)
              }}
            />
          </label>

          {selectedFiles.length > 0 && (
            <ul className="mb-4 space-y-1 text-sm text-gray-600">
              {selectedFiles.map((f) => (
                <li key={f.name} className="flex items-center gap-2">
                  <span className="text-green-500">✓</span>
                  {f.name} ({(f.size / 1024).toFixed(1)} KB)
                </li>
              ))}
            </ul>
          )}

          {mutation.isError && (
            <p className="mb-4 text-sm text-red-500">
              Fehler beim Hochladen. {uploadErrorMessage}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <button
              onClick={() => navigate(`/accounts/${accountId}`)}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Abbrechen
            </button>
            <button
              onClick={() => mutation.mutate()}
              disabled={selectedFiles.length === 0 || mutation.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {mutation.isPending ? 'Importiere …' : 'Importieren'}
            </button>
          </div>
        </div>
      )}

      {step === 'result' && (
        <div className="space-y-4">
          {results.map((run) => (
            <ImportRunCard key={run.id} run={run} />
          ))}
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setStep('upload')
                setSelectedFiles([])
                setResults([])
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Weiterer Import
            </button>
            <Link
              to={`/accounts/${accountId}`}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
            >
              Zum Konto
            </Link>
          </div>
        </div>
      )}

      {/* Import history */}
      {history && history.items.length > 0 && step === 'upload' && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Import-Verlauf
          </h2>
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs font-medium uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-2 text-left">Datei</th>
                  <th className="px-4 py-2 text-left">Zeilen</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Datum</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {history.items.map((run) => (
                  <tr key={run.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono text-xs">{run.filename}</td>
                    <td className="px-4 py-2 text-gray-600">{run.row_count}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-2 text-gray-400">
                      {new Date(run.created_at + 'Z').toLocaleDateString('de-DE', { timeZone: 'Europe/Vienna' })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function ImportRunCard({ run }: Readonly<{ run: ImportRunDetail }>) {
  const [showDuplicates, setShowDuplicates] = useState(false)
  const hasErrors = run.error_count > 0
  const duplicates: ImportDuplicateInfo[] = run.error_details?.duplicates ?? []
  const zeroAmountSkipped: number = run.error_details?.zero_amount_skipped ?? 0
  const realDuplicateCount = duplicates.length
  let skippedLabel: string
  if (realDuplicateCount > 0 && zeroAmountSkipped > 0) {
    const pluralSuffix = realDuplicateCount === 1 ? '' : 'e'
    skippedLabel = `Übersprungen: ${run.skipped_count} (${realDuplicateCount} Duplikat${pluralSuffix}, ${zeroAmountSkipped} Betrag 0)`
  } else if (realDuplicateCount > 0) {
    skippedLabel = `Duplikate: ${realDuplicateCount}`
  } else {
    skippedLabel = `Übersprungen: ${zeroAmountSkipped} (Betrag 0)`
  }

  return (
    <div
      className={`rounded-xl border p-4 ${
        hasErrors ? 'border-orange-200 bg-orange-50' : 'border-green-200 bg-green-50'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-gray-800">{run.filename}</span>
        <StatusBadge status={run.status} />
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-sm text-gray-600">
        <span>Importiert: <strong>{run.row_count}</strong></span>
        {run.skipped_count > 0 && (
          realDuplicateCount > 0 ? (
            <button
              onClick={() => setShowDuplicates((v) => !v)}
              className="text-amber-600 hover:underline"
            >
              <strong>{skippedLabel}</strong> {showDuplicates ? '▲' : '▼'}
            </button>
          ) : (
            <span className="text-gray-500">{skippedLabel}</span>
          )
        )}
        {hasErrors && (
          <span className="text-orange-600">Parse-Fehler: <strong>{run.error_count}</strong></span>
        )}
      </div>

      {showDuplicates && duplicates.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-lg border border-amber-200 bg-white">
          <div className="bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700">
            Diese Zeilen existieren bereits im Journal und wurden übersprungen:
          </div>
          <table className="w-full text-xs">
            <thead className="border-b border-amber-100 bg-amber-50/50">
              <tr>
                <th className="px-3 py-1.5 text-left text-gray-500">CSV-Zeile</th>
                <th className="px-3 py-1.5 text-left text-gray-500">Valuta</th>
                <th className="px-3 py-1.5 text-right text-gray-500">Betrag</th>
                <th className="px-3 py-1.5 text-left text-gray-500">Text / Partner</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-amber-50">
              {duplicates.map((d) => (
                <tr
                  key={`${d.row ?? 'na'}-${d.valuta_date}-${d.amount}-${d.text ?? d.partner_name_raw ?? 'na'}`}
                  className="hover:bg-amber-50"
                >
                  <td className="px-3 py-1.5 font-mono text-gray-400">{d.row ?? '–'}</td>
                  <td className="px-3 py-1.5 font-mono text-gray-600">{d.valuta_date}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-gray-800">
                    {Number(d.amount).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                  </td>
                  <td className="max-w-xs truncate px-3 py-1.5 text-gray-600">
                    {d.text ?? d.partner_name_raw ?? '–'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }: Readonly<{ status: string }>) {
  const styles: Record<string, string> = {
    completed: 'bg-green-100 text-green-700',
    processing: 'bg-blue-100 text-blue-700',
    failed: 'bg-red-100 text-red-700',
    pending: 'bg-gray-100 text-gray-500',
  }
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${styles[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}

function StepBadge({
  number,
  label,
  active,
  done,
}: Readonly<{
  number: number
  label: string
  active: boolean
  done: boolean
}>) {
  let badgeClass = 'bg-gray-200 text-gray-500'
  if (done) {
    badgeClass = 'bg-green-500 text-white'
  } else if (active) {
    badgeClass = 'bg-blue-600 text-white'
  }

  return (
    <div className="flex items-center gap-2">
      <div
        className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${badgeClass}`}
      >
        {done ? '✓' : number}
      </div>
      <span
        className={`text-sm font-medium ${active ? 'text-gray-900' : 'text-gray-400'}`}
      >
        {label}
      </span>
    </div>
  )
}
