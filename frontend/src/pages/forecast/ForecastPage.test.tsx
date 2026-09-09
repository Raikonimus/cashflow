import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { ForecastPage } from './ForecastPage'

type PayloadRecord = Record<string, unknown> & {
  params?: Record<string, unknown>
}

const MANDANT_ID = 'mandant-1'
const SERVICE_ID = 'service-1'
const OVERVIEW_URL = `/api/v1/mandants/${MANDANT_ID}/forecast/services`
const RULE_URL = `/api/v1/mandants/${MANDANT_ID}/services/${SERVICE_ID}/forecast-rule`
const PLANNED_URL = `/api/v1/mandants/${MANDANT_ID}/forecast/planned-items`
const SNAPSHOTS_URL = `/api/v1/mandants/${MANDANT_ID}/forecast/snapshots`

function overviewRow(overrides: Record<string, unknown> = {}) {
  return {
    service_id: SERVICE_ID,
    service_name: 'Gehalt',
    partner_id: 'partner-1',
    partner_name: 'Mitarbeiter',
    section: 'expense',
    mode: 'auto',
    effective_rule_type: 'fixed_recurring',
    effective_reason: 'Monatlich, stabiler Betrag',
    confidence: 'high',
    detected_cadence: 'monthly',
    occurrence_count: 20,
    last_booking_period: '2026-08',
    next_12_months: '-39000.00',
    planned_item_count: 0,
    adjustment_pct: '0.00',
    shift_months: 0,
    customised: false,
    relative_error: null,
    backtest_ran: false,
    beats_baseline: false,
    replaced_detected: false,
    service_stopped: false,
    ...overrides,
  }
}

function backtest(overrides: Record<string, unknown> = {}) {
  return {
    ran: true,
    reason: 'Rückvergleich über 6 Monate',
    holdout_months: 6,
    holdout_from: '2026-03',
    holdout_to: '2026-08',
    actual_volume: '18000.00',
    relative_error: '0.0400',
    spread: '0.0500',
    beats_baseline: true,
    replaced_detected: false,
    service_stopped: false,
    candidates: [
      {
        key: 'detected',
        label: 'Erkanntes Muster',
        mae: '120.00',
        level_error: '300.00',
        score: '85.00',
        is_baseline: false,
        is_winner: true,
      },
      {
        key: 'none',
        label: 'Nullprognose (Vergleich)',
        mae: '3000.00',
        level_error: '18000.00',
        score: '3000.00',
        is_baseline: true,
        is_winner: false,
      },
    ],
    ...overrides,
  }
}

function ruleResponse(overrides: Record<string, unknown> = {}) {
  return {
    service_id: SERVICE_ID,
    service_name: 'Gehalt',
    partner_name: 'Mitarbeiter',
    mode: 'auto',
    rule_type: null,
    params: null,
    adjustment_pct: '0.00',
    shift_months: 0,
    detected_cadence: 'monthly',
    detected_rule_type: 'fixed_recurring',
    detected_reason: 'Monatlich, stabiler Betrag (Median aus 20 Buchungen)',
    occurrence_count: 20,
    median_amount: '-3000.00',
    effective_rule_type: 'fixed_recurring',
    effective_reason: 'Monatlich, stabiler Betrag (Median aus 20 Buchungen)',
    confidence: 'high',
    preview: [
      { period: '2026-09', amount: '-3000.00', is_planned: false },
      { period: '2026-10', amount: '-3000.00', is_planned: false },
    ],
    backtest: backtest(),
    ...overrides,
  }
}

function setup(role = 'accountant') {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role, mandant_id: MANDANT_ID },
      selectedMandant: { id: MANDANT_ID, name: 'Test' },
      mandants: [],
    })
  })
}

function overviewPayload(rows: unknown[], overrides: Record<string, unknown> = {}) {
  return {
    services: rows,
    total: rows.length,
    without_rule: 0,
    customised: 0,
    backtested: 0,
    replaced_by_backtest: 0,
    stopped_by_backtest: 0,
    weak_forecasts: 0,
    median_relative_error: null,
    ...overrides,
  }
}

function mockOverview(rows = [overviewRow()], overrides: Record<string, unknown> = {}) {
  server.use(
    http.get(OVERVIEW_URL, () => HttpResponse.json(overviewPayload(rows, overrides))),
    http.get(SNAPSHOTS_URL, () => HttpResponse.json([])),
  )
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ForecastPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openEditor() {
  await userEvent.click(await screen.findByRole('button', { name: 'Regel bearbeiten' }))
  return screen.findByText(/Erkanntes Muster/)
}

describe('ForecastPage – Übersicht', () => {
  beforeEach(() => setup())

  it('listet Leistungen mit Regel, Confidence und Relevanz', async () => {
    mockOverview()
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).getByText('Fester Betrag')).toBeInTheDocument()
    expect(within(row).getByText('hoch')).toBeInTheDocument()
    expect(within(row).getByText('-39.000 €')).toBeInTheDocument()
  })

  it('kennzeichnet händisch gesetzte und abgeschaltete Regeln', async () => {
    mockOverview([
      overviewRow({ mode: 'manual' }),
      overviewRow({
        service_id: 'service-2',
        service_name: 'Miete',
        mode: 'off',
        effective_rule_type: 'none',
        confidence: null,
      }),
    ])
    renderPage()

    expect(await screen.findByText('händisch')).toBeInTheDocument()
    expect(screen.getByText('aus')).toBeInTheDocument()
  })

  it('nennt die Zahl der angezeigten Leistungen', async () => {
    mockOverview([overviewRow()], { without_rule: 7, total: 8 })
    renderPage()

    expect(await screen.findByText(/1 von 8 Leistungen/)).toBeInTheDocument()
  })

  it('reicht den Filter an die API weiter', async () => {
    const calls: string[] = []
    server.use(
      http.get(OVERVIEW_URL, ({ request }) => {
        calls.push(new URL(request.url).search)
        return HttpResponse.json(overviewPayload([]))
      }),
    )
    server.use(http.get(SNAPSHOTS_URL, () => HttpResponse.json([])))
    renderPage()
    await screen.findByText(/Keine Leistungen gefunden/)

    await userEvent.selectOptions(screen.getByLabelText('Auswahl einschränken'), 'without_rule')

    await waitFor(() => expect(calls.at(-1)).toContain('only_without_rule=true'))
  })

  it('reicht die Suche an die API weiter', async () => {
    const calls: string[] = []
    server.use(
      http.get(OVERVIEW_URL, ({ request }) => {
        calls.push(new URL(request.url).search)
        return HttpResponse.json(overviewPayload([]))
      }),
    )
    server.use(http.get(SNAPSHOTS_URL, () => HttpResponse.json([])))
    renderPage()
    await screen.findByText(/Keine Leistungen gefunden/)

    await userEvent.type(screen.getByLabelText('Leistung oder Partner suchen'), 'miete')

    await waitFor(() => expect(calls.at(-1)).toContain('search=miete'))
  })
})

describe('ForecastPage – Handgesetztes erkennen', () => {
  beforeEach(() => setup())

  it('markiert eine Anpassung, obwohl der Modus automatisch bleibt', async () => {
    // Genau der Fall, der in der Praxis untergegangen ist.
    mockOverview([overviewRow({ adjustment_pct: '100.00', customised: true })], {
      customised: 1,
    })
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).getByText('+100 %')).toBeInTheDocument()
    expect(within(row).queryByText('händisch')).not.toBeInTheDocument()
  })

  it('zeigt eine Kuerzung mit Minuszeichen', async () => {
    mockOverview([overviewRow({ adjustment_pct: '-10.00', customised: true })], {
      customised: 1,
    })
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).getByText('\u221210 %')).toBeInTheDocument()
  })

  it('markiert Zahlungsverzug und Planposten', async () => {
    mockOverview([overviewRow({ shift_months: 2, planned_item_count: 3, customised: true })], {
      customised: 1,
    })
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).getByText('+2 Mon.')).toBeInTheDocument()
    expect(within(row).getByText('3 Planposten')).toBeInTheDocument()
  })

  it('laesst eine unberuehrte Leistung unmarkiert', async () => {
    mockOverview()
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).queryByText(/%/)).not.toBeInTheDocument()
    expect(within(row).queryByText(/Mon\./)).not.toBeInTheDocument()
    expect(within(row).queryByText(/Planposten/)).not.toBeInTheDocument()
    // Der Zaehler in der Kopfzeile erscheint erst, wenn es etwas zu zaehlen gibt.
    // ("Von Hand angepasst" steht dauerhaft in der Filterauswahl.)
    expect(screen.queryByRole('button', { name: /angepasst/ })).not.toBeInTheDocument()
  })

  it('filtert ueber die Kopfzeile auf die angepassten Leistungen', async () => {
    mockOverview(
      [
        overviewRow(),
        overviewRow({
          service_id: 'service-2',
          service_name: 'Lizenzen',
          adjustment_pct: '15.00',
          customised: true,
        }),
      ],
      { customised: 1 },
    )
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '1 angepasst' }))

    await waitFor(() => expect(screen.queryByText('Gehalt')).not.toBeInTheDocument())
    expect(screen.getByText('Lizenzen')).toBeInTheDocument()
  })
})

describe('ForecastPage – Treffsicherheit', () => {
  beforeEach(() => setup())

  it('zeigt den gemessenen Fehler statt der geschätzten Confidence', async () => {
    mockOverview([
      overviewRow({ backtest_ran: true, beats_baseline: true, relative_error: '0.3663' }),
    ])
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).getByText('±37 %')).toBeInTheDocument()
    // Die geschätzte Confidence tritt zurück, sobald gemessen wurde.
    expect(within(row).queryByText('hoch')).not.toBeInTheDocument()
  })

  it('faellt ohne Messung auf die geschaetzte Confidence zurueck', async () => {
    mockOverview([overviewRow()])
    renderPage()

    const row = await screen.findByRole('row', { name: /Gehalt/ })
    expect(within(row).getByText('hoch')).toBeInTheDocument()
  })

  it('kennzeichnet beendete und schwache Prognosen', async () => {
    mockOverview([
      overviewRow({ backtest_ran: true, service_stopped: true }),
      overviewRow({
        service_id: 'service-2',
        service_name: 'Projekte',
        backtest_ran: true,
        beats_baseline: false,
        relative_error: '0.9000',
      }),
    ])
    renderPage()

    expect(await screen.findByText('beendet')).toBeInTheDocument()
    expect(screen.getByText('schwach')).toBeInTheDocument()
  })

  it('fasst die Messung ueber alle Leistungen zusammen', async () => {
    mockOverview([overviewRow()], {
      total: 410,
      backtested: 132,
      replaced_by_backtest: 36,
      stopped_by_backtest: 67,
      weak_forecasts: 6,
      median_relative_error: '0.3663',
    })
    renderPage()

    expect(await screen.findByText('Rückverglichen')).toBeInTheDocument()
    expect(screen.getByText('132')).toBeInTheDocument()
    expect(screen.getByText('±37 %')).toBeInTheDocument()
    expect(screen.getByText('67')).toBeInTheDocument()
  })

  it('filtert auf die schwachen Prognosen', async () => {
    mockOverview(
      [
        overviewRow({ backtest_ran: true, beats_baseline: true }),
        overviewRow({
          service_id: 'service-2',
          service_name: 'Projekte',
          backtest_ran: true,
          beats_baseline: false,
        }),
      ],
      { weak_forecasts: 1 },
    )
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Anzeigen' }))

    await waitFor(() => expect(screen.queryByText('Gehalt')).not.toBeInTheDocument())
    expect(screen.getByText('Projekte')).toBeInTheDocument()
  })
})

describe('ForecastPage – Regel-Editor', () => {
  beforeEach(() => {
    setup()
    mockOverview()
    server.use(
      http.get(RULE_URL, () => HttpResponse.json(ruleResponse())),
      http.get(PLANNED_URL, () => HttpResponse.json([])),
    )
  })

  it('zeigt erkanntes Muster und Vorschau', async () => {
    renderPage()
    await openEditor()

    expect(screen.getByText(/monatlich, 20 Buchungen, Median -3.000,00 €/)).toBeInTheDocument()
    expect(screen.getByText('Sep 26')).toBeInTheDocument()
  })

  it('speichert eine händisch gesetzte Regel', async () => {
    let payload: Record<string, unknown> | null = null
    server.use(
      http.put(RULE_URL, async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(ruleResponse({ mode: 'manual', rule_type: 'fixed_recurring' }))
      }),
    )
    renderPage()
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Händisch' }))
    const amount = screen.getByLabelText('Betrag je Zahlung')
    await userEvent.clear(amount)
    await userEvent.type(amount, '-4500')
    await userEvent.click(screen.getByRole('button', { name: 'Regel speichern' }))

    await waitFor(() => expect(payload).not.toBeNull())
    expect(payload).toMatchObject({
      mode: 'manual',
      rule_type: 'fixed_recurring',
      params: { amount: '-4500.00', interval_months: 1 },
    })
  })

  it('überträgt Sondermonate mit Faktor', async () => {
    let payload: PayloadRecord | null = null
    server.use(
      http.put(RULE_URL, async ({ request }) => {
        payload = (await request.json()) as PayloadRecord
        return HttpResponse.json(ruleResponse())
      }),
    )
    renderPage()
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Händisch' }))
    await userEvent.click(screen.getByRole('button', { name: 'Jun', pressed: false }))
    await userEvent.click(screen.getByRole('button', { name: 'Regel speichern' }))

    const gesendet = payload as PayloadRecord | null
    await waitFor(() => expect(payload).not.toBeNull())
    expect(gesendet?.params).toMatchObject({ special_months: { '6': '2' } })
  })

  it('überträgt Anpassung und Zahlungsverzug auch im Automatikmodus', async () => {
    let payload: PayloadRecord | null = null
    server.use(
      http.put(RULE_URL, async ({ request }) => {
        payload = (await request.json()) as PayloadRecord
        return HttpResponse.json(ruleResponse())
      }),
    )
    renderPage()
    await openEditor()

    const adjustment = screen.getByLabelText('Anpassung in %')
    await userEvent.clear(adjustment)
    await userEvent.type(adjustment, '3')
    await userEvent.selectOptions(screen.getByLabelText('Zahlungsverzug'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Regel speichern' }))

    await waitFor(() => expect(payload).not.toBeNull())
    expect(payload).toMatchObject({ mode: 'auto', adjustment_pct: '3.00', shift_months: 2 })
  })

  it('schaltet die Prognose ab', async () => {
    let payload: PayloadRecord | null = null
    server.use(
      http.put(RULE_URL, async ({ request }) => {
        payload = (await request.json()) as PayloadRecord
        return HttpResponse.json(ruleResponse({ mode: 'off' }))
      }),
    )
    renderPage()
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Keine Prognose' }))
    await userEvent.click(screen.getByRole('button', { name: 'Regel speichern' }))
    const gesendet = payload as PayloadRecord | null

    await waitFor(() => expect(payload).not.toBeNull())
    expect(gesendet?.mode).toBe('off')
  })

  it('setzt auf Automatik zurück', async () => {
    let called = false
    server.use(
      http.delete(RULE_URL, () => {
        called = true
        return HttpResponse.json(ruleResponse())
      }),
    )
    renderPage()
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Auf Automatik zurücksetzen' }))

    await waitFor(() => expect(called).toBe(true))
  })

  it('meldet einen Serverfehler statt ihn zu verschlucken', async () => {
    server.use(
      http.put(RULE_URL, () =>
        HttpResponse.json({ detail: 'Regeltyp passt nicht' }, { status: 400 }),
      ),
    )
    renderPage()
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Regel speichern' }))

    expect(await screen.findByText('Regeltyp passt nicht')).toBeInTheDocument()
  })
})

describe('ForecastPage – Planposten', () => {
  beforeEach(() => {
    setup()
    mockOverview()
    server.use(http.get(RULE_URL, () => HttpResponse.json(ruleResponse())))
  })

  it('legt einen Planposten an', async () => {
    let payload: PayloadRecord | null = null
    server.use(
      http.get(PLANNED_URL, () => HttpResponse.json([])),
      http.post(PLANNED_URL, async ({ request }) => {
        payload = (await request.json()) as PayloadRecord
        return HttpResponse.json({ id: 'p1', ...payload }, { status: 201 })
      }),
    )
    renderPage()
    await openEditor()

    const amount = screen.getByLabelText('Betrag')
    await userEvent.type(amount, '30000')
    await userEvent.type(screen.getByLabelText('Notiz'), 'Rechnung 114')
    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }))

    await waitFor(() => expect(payload).not.toBeNull())
    expect(payload).toMatchObject({
      service_id: SERVICE_ID,
      amount: '30000.00',
      note: 'Rechnung 114',
    })
  })

  it('lehnt einen leeren Betrag ab', async () => {
    server.use(http.get(PLANNED_URL, () => HttpResponse.json([])))
    renderPage()
    await openEditor()

    await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }))

    expect(await screen.findByText(/Bitte einen Betrag eingeben/)).toBeInTheDocument()
  })

  it('listet bestehende Posten und erlaubt das Entfernen', async () => {
    let deleted = false
    server.use(
      http.get(PLANNED_URL, () =>
        HttpResponse.json([
          {
            id: 'p1',
            service_id: SERVICE_ID,
            service_name: 'Gehalt',
            partner_name: null,
            period: '2027-04',
            amount: '-9999.00',
            note: 'Abfertigung',
            created_at: '2026-09-09T00:00:00Z',
            updated_at: '2026-09-09T00:00:00Z',
            status: 'active',
            remaining_in_month: '-9999.00',
          },
        ]),
      ),
      http.delete(`${PLANNED_URL}/p1`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderPage()
    await openEditor()

    expect(await screen.findByText('Abfertigung')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Entfernen' }))

    await waitFor(() => expect(deleted).toBe(true))
  })
})

describe('ForecastPage – Rechte', () => {
  it('zeigt Viewern keine Bearbeitungsmöglichkeit', async () => {
    setup('viewer')
    mockOverview()
    server.use(
      http.get(RULE_URL, () => HttpResponse.json(ruleResponse())),
      http.get(PLANNED_URL, () => HttpResponse.json([])),
    )
    renderPage()
    await openEditor()

    expect(screen.queryByRole('button', { name: 'Regel speichern' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hinzufügen' })).not.toBeInTheDocument()
  })
})

describe('ForecastPage – Planposten im Editor', () => {
  function plannedItem(overrides: Record<string, unknown> = {}) {
    return {
      id: 'item-1',
      service_id: SERVICE_ID,
      service_name: 'Gehalt',
      partner_name: 'Mitarbeiter',
      period: '2027-04',
      amount: '-5000.00',
      note: null,
      created_at: '2026-09-09T08:00:00Z',
      updated_at: '2026-09-09T08:00:00Z',
      status: 'active',
      remaining_in_month: '-5000.00',
      ...overrides,
    }
  }

  async function openWith(items: unknown[]) {
    setup()
    mockOverview()
    server.use(
      http.get(RULE_URL, () => HttpResponse.json(ruleResponse())),
      http.get(PLANNED_URL, () => HttpResponse.json(items)),
    )
    renderPage()
    await openEditor()
  }

  it('zeigt einen kuenftigen Posten ohne Zusatz', async () => {
    await openWith([plannedItem()])

    expect(await screen.findByText('-5.000,00 €')).toBeInTheDocument()
    expect(screen.queryByText('verbraucht')).not.toBeInTheDocument()
    expect(screen.queryByText('abgelaufen')).not.toBeInTheDocument()
  })

  it('nennt beim teilweise gebuchten Posten den Rest', async () => {
    await openWith([
      plannedItem({ period: '2026-09', status: 'partly_used', remaining_in_month: '-2000.00' }),
    ])

    expect(await screen.findByText('teilweise gebucht')).toBeInTheDocument()
    expect(screen.getByText(/noch -2\.000,00 €/)).toBeInTheDocument()
  })

  it('streicht einen verbrauchten Posten durch', async () => {
    await openWith([plannedItem({ period: '2026-09', status: 'used', remaining_in_month: '0.00' })])

    expect(await screen.findByText('verbraucht')).toBeInTheDocument()
    expect(screen.getByText('-5.000,00 €').className).toContain('line-through')
  })

  it('kennzeichnet einen abgelaufenen Posten', async () => {
    await openWith([
      plannedItem({ period: '2026-07', status: 'expired', remaining_in_month: '0.00' }),
    ])

    const badge = await screen.findByText('abgelaufen')
    expect(badge).toBeInTheDocument()
    expect(badge.getAttribute('title')).toMatch(/wirkt nicht mehr/)
  })

  it('bleibt bei einem unbekannten Status bedienbar', async () => {
    // Ein neuer Statuswert aus dem Backend darf den Editor nicht sprengen.
    await openWith([plannedItem({ status: 'irgendwas_neues' })])

    expect(await screen.findByText('-5.000,00 €')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Entfernen' })).toBeInTheDocument()
  })

  it('laesst auch wirkungslose Posten entfernen', async () => {
    await openWith([
      plannedItem({ period: '2026-07', status: 'expired', remaining_in_month: '0.00' }),
    ])

    expect(await screen.findByRole('button', { name: 'Entfernen' })).toBeInTheDocument()
  })
})

describe('ForecastPage – Rückvergleich im Editor', () => {
  beforeEach(() => {
    setup()
    mockOverview()
    server.use(http.get(PLANNED_URL, () => HttpResponse.json([])))
  })

  async function open(rule: Record<string, unknown>) {
    server.use(http.get(RULE_URL, () => HttpResponse.json(rule)))
    renderPage()
    await openEditor()
  }

  it('nennt Pruefzeitraum und gemessenen Fehler', async () => {
    await open(ruleResponse())

    expect(await screen.findByText(/Geprüft an 6 Monaten/)).toBeInTheDocument()
    expect(screen.getByText('±4 %')).toBeInTheDocument()
  })

  it('klappt die Kandidatentabelle mit der Nullprognose auf', async () => {
    await open(ruleResponse())

    await userEvent.click(await screen.findByRole('button', { name: /geprüften Regeln/ }))

    expect(screen.getByText('Erkanntes Muster ✓')).toBeInTheDocument()
    expect(screen.getByText('Nullprognose (Vergleich)')).toBeInTheDocument()
    expect(screen.getByText(/wird aber nie gewählt/)).toBeInTheDocument()
  })

  it('warnt, wenn die Regel schlechter trifft als gar keine', async () => {
    await open(ruleResponse({ backtest: backtest({ beats_baseline: false }) }))

    expect(await screen.findByText(/trifft schlechter als gar keine Prognose/)).toBeInTheDocument()
  })

  it('erklaert eine als beendet erkannte Leistung', async () => {
    await open(
      ruleResponse({
        backtest: backtest({
          service_stopped: true,
          beats_baseline: false,
          reason: '03/2026–08/2026 ohne jede Buchung — Leistung gilt als beendet',
        }),
      }),
    )

    expect(await screen.findByText(/Prognose ist damit abgeschaltet/)).toBeInTheDocument()
    // Nicht zusätzlich als "schwach" beklagen — das wäre dieselbe Sache zweimal.
    expect(screen.queryByText(/trifft schlechter als gar keine/)).not.toBeInTheDocument()
  })

  it('sagt es, wenn die Historie fuer einen Rueckvergleich nicht reicht', async () => {
    await open(
      ruleResponse({
        backtest: {
          ran: false,
          reason: 'Historie reicht nicht: 12 Monate vor dem 6-Monats-Prüfzeitraum nötig',
          holdout_months: 6,
          holdout_from: null,
          holdout_to: null,
          actual_volume: '0.00',
          relative_error: null,
          spread: null,
          beats_baseline: false,
          replaced_detected: false,
          service_stopped: false,
          candidates: [],
        },
      }),
    )

    expect(
      await screen.findByText(/Bandbreite dieser Leistung ist deshalb geschätzt/),
    ).toBeInTheDocument()
  })
})

describe('ForecastPage – Plan gegen Ist', () => {
  const SNAPSHOT_ID = 'snap-1'

  function snapshot(overrides: Record<string, unknown> = {}) {
    return {
      id: SNAPSHOT_ID,
      label: 'Vor der Budgetrunde',
      scenario: 'expected',
      as_of: '2026-09-15',
      currency: 'EUR',
      start_balance: '86075.45',
      created_at: '2026-09-15T08:00:00Z',
      month_count: 16,
      elapsed_months: 1,
      latest_deviation: '-500.00',
      ...overrides,
    }
  }

  beforeEach(() => {
    setup()
    mockOverview()
    server.use(http.get(PLANNED_URL, () => HttpResponse.json([])))
  })

  it('meldet, wenn noch kein Planstand existiert', async () => {
    renderPage()

    expect(await screen.findByText('Noch kein Planstand festgehalten.')).toBeInTheDocument()
  })

  it('listet Planstaende mit der aufgelaufenen Abweichung', async () => {
    server.use(http.get(SNAPSHOTS_URL, () => HttpResponse.json([snapshot()])))
    renderPage()

    const row = await screen.findByRole('row', { name: /Vor der Budgetrunde/ })
    expect(within(row).getByText('15.09.2026')).toBeInTheDocument()
    expect(within(row).getByText('-500 €')).toBeInTheDocument()
  })

  it('legt einen Planstand an', async () => {
    const posted: PayloadRecord[] = []
    let created = false
    server.use(
      http.get(SNAPSHOTS_URL, () => HttpResponse.json(created ? [snapshot()] : [])),
      http.post(SNAPSHOTS_URL, async ({ request }) => {
        posted.push((await request.json()) as PayloadRecord)
        created = true
        return HttpResponse.json(snapshot(), { status: 201 })
      }),
      http.get(`${SNAPSHOTS_URL}/${SNAPSHOT_ID}`, () =>
        HttpResponse.json({ ...snapshot(), months: [], mean_absolute_deviation: null }),
      ),
    )
    renderPage()

    await userEvent.type(await screen.findByLabelText('Bezeichnung des Planstands'), 'Budgetrunde')
    await userEvent.click(screen.getByRole('button', { name: 'Planstand festhalten' }))

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0].label).toBe('Budgetrunde')
  })

  it('zeigt Plan und Ist je Monat', async () => {
    server.use(
      http.get(SNAPSHOTS_URL, () => HttpResponse.json([snapshot()])),
      http.get(`${SNAPSHOTS_URL}/${SNAPSHOT_ID}`, () =>
        HttpResponse.json({
          ...snapshot(),
          mean_absolute_deviation: '500.00',
          months: [
            {
              period: '2026-09',
              planned_net: '-3000.00',
              planned_closing: '83075.45',
              actual_net: '-3500.00',
              actual_closing: '82575.45',
              net_deviation: '-500.00',
              deviation: '-500.00',
              is_complete: true,
            },
            {
              period: '2026-10',
              planned_net: '-3000.00',
              planned_closing: '80075.45',
              actual_net: null,
              actual_closing: null,
              net_deviation: null,
              deviation: null,
              is_complete: false,
            },
          ],
        }),
      ),
    )
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Vergleich' }))

    expect(await screen.findByText(/im Mittel um/)).toBeInTheDocument()
    // Die Vergleichstabelle steckt in der aufgeklappten Zeile der äußeren Tabelle.
    const tables = screen.getAllByRole('table')
    const detail = within(tables[tables.length - 1])

    const september = detail.getByRole('row', { name: /Sep 26/ })
    expect(within(september).getByText('-3.500 €')).toBeInTheDocument()
    // Der künftige Monat bleibt leer statt eine Null vorzutäuschen.
    const october = detail.getByRole('row', { name: /Okt 26/ })
    expect(within(october).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('haelt den Vergleich zurueck, solange kein Monat abgelaufen ist', async () => {
    server.use(
      http.get(SNAPSHOTS_URL, () =>
        HttpResponse.json([snapshot({ elapsed_months: 0, latest_deviation: null })]),
      ),
      http.get(`${SNAPSHOTS_URL}/${SNAPSHOT_ID}`, () =>
        HttpResponse.json({
          ...snapshot({ elapsed_months: 0, latest_deviation: null }),
          mean_absolute_deviation: null,
          months: [],
        }),
      ),
    )
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Vergleich' }))

    expect(await screen.findByText(/Noch kein Monat vollständig abgelaufen/)).toBeInTheDocument()
  })
})
