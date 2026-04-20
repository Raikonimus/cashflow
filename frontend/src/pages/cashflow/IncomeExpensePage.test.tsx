import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { IncomeExpensePage } from './IncomeExpensePage'

const MANDANT_ID = 'mandant-1'

function makeCells(netValue: string) {
  return {
    year_total: { gross: netValue, net: netValue },
    jan: { gross: netValue, net: netValue },
    feb: { gross: '0.00', net: '0.00' },
    mar: { gross: '0.00', net: '0.00' },
    apr: { gross: '0.00', net: '0.00' },
    may: { gross: '0.00', net: '0.00' },
    jun: { gross: '0.00', net: '0.00' },
    jul: { gross: '0.00', net: '0.00' },
    aug: { gross: '0.00', net: '0.00' },
    sep: { gross: '0.00', net: '0.00' },
    oct: { gross: '0.00', net: '0.00' },
    nov: { gross: '0.00', net: '0.00' },
    dec: { gross: '0.00', net: '0.00' },
  }
}

function setup(role = 'viewer') {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role, mandant_id: MANDANT_ID },
      selectedMandant: { id: MANDANT_ID, name: 'Test' },
      mandants: [],
    })
  })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <IncomeExpensePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function createDataTransfer() {
  const store = new Map<string, string>()
  return {
    effectAllowed: 'all',
    setData: (type: string, value: string) => {
      store.set(type, value)
    },
    getData: (type: string) => store.get(type) ?? '',
    clearData: () => {
      store.clear()
    },
    dropEffect: 'move',
    files: [],
    items: [],
    types: [],
  }
}

function buildIncomeMatrixResponse(groups: Array<Record<string, unknown>>, total = '100.00') {
  return {
    year: 2026,
    base_currency: 'EUR',
    sections: {
      income: {
        currency: 'EUR',
        excluded_currency_count: 0,
        excluded_currency_amount_gross: '0.00',
        groups,
        totals: makeCells(total),
      },
      expense: {
        currency: 'EUR',
        excluded_currency_count: 0,
        excluded_currency_amount_gross: '0.00',
        groups: [],
        totals: makeCells('0.00'),
      },
      neutral: {
        currency: 'EUR',
        excluded_currency_count: 0,
        excluded_currency_amount_gross: '0.00',
        groups: [],
        totals: makeCells('0.00'),
      },
    },
  }
}

afterEach(() => {
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
  })
})

beforeEach(() => {
  server.use(
    http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2026] })),
  )
})

describe('IncomeExpensePage', () => {
  it('renders the matrix in read-only mode for viewer users', async () => {
    setup('viewer')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () =>
        HttpResponse.json({
          year: 2026,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-income',
                  group_name: 'Wiederkehrend',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 4,
                  active_years: [2026],
                  subtotal_cells: makeCells('3050.00'),
                  services: [
                    {
                      service_id: 'service-income',
                      service_name: 'Beratung',
                      partner_name: 'Beispiel GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('1200.00'),
                    },
                    {
                      service_id: 'service-top',
                      service_name: 'Premium',
                      partner_name: 'Beispiel GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('1800.00'),
                    },
                    {
                      service_id: 'service-same-name',
                      service_name: 'Adobe',
                      partner_name: 'Adobe',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('50.00'),
                    },
                    {
                      service_id: 'service-zero',
                      service_name: 'Nullzeile',
                      partner_name: 'Beispiel GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('0.00'),
                    },
                  ],
                },
                {
                  group_id: 'group-hidden',
                  group_name: 'Leergruppe',
                  sort_order: 2,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [2026],
                  subtotal_cells: makeCells('0.00'),
                  services: [
                    {
                      service_id: 'service-hidden',
                      service_name: 'Versteckt',
                      partner_name: 'Versteckt GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('0.00'),
                    },
                  ],
                },
              ],
              totals: makeCells('3050.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 1,
              excluded_currency_amount_gross: '19.99',
              groups: [
                {
                  group_id: 'group-expense',
                  group_name: 'Betrieb',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [2026],
                  subtotal_cells: makeCells('250.00'),
                  services: [
                    {
                      service_id: 'service-expense',
                      service_name: 'Basisleistung',
                      partner_name: 'Amazon EU',
                      service_type: 'supplier',
                      erfolgsneutral: false,
                      cells: makeCells('250.00'),
                    },
                  ],
                },
              ],
              totals: makeCells('250.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Beispiel GmbH / Premium')).toBeInTheDocument())
    expect(screen.getByText('Beispiel GmbH / Beratung')).toBeInTheDocument()
    expect(screen.getByText('Adobe')).toBeInTheDocument()
    expect(screen.queryByText('Adobe/Adobe')).not.toBeInTheDocument()
    expect(screen.getByText('Amazon EU')).toBeInTheDocument()
    expect(screen.queryByText('Beratung')).not.toBeInTheDocument()
    expect(screen.queryByText('Basisleistung')).not.toBeInTheDocument()
    expect(screen.queryByText('Nullzeile')).not.toBeInTheDocument()
    expect(screen.queryByText('Leergruppe')).not.toBeInTheDocument()
    expect(screen.getByText(/Alle Angaben in €/i)).toBeInTheDocument()
    expect(screen.getByText(/Read-only Modus/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /gruppe anlegen/i })).not.toBeInTheDocument()
    expect(screen.getAllByText(/3[. ]?050/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/250/).length).toBeGreaterThan(0)

    const incomeSection = screen.getByRole('heading', { name: 'Einnahmen' }).closest('section')
    expect(incomeSection).not.toBeNull()
    const incomeRows = within(incomeSection).getAllByRole('row')
    const incomeText = incomeRows.map((row) => row.textContent ?? '')
    const premiumIndex = incomeText.findIndex((text) => text.includes('Beispiel GmbH / Premium'))
    const beratungIndex = incomeText.findIndex((text) => text.includes('Beispiel GmbH / Beratung'))
    const adobeIndex = incomeText.findIndex((text) => text.includes('Adobe'))
    expect(premiumIndex).toBeGreaterThan(-1)
    expect(beratungIndex).toBeGreaterThan(-1)
    expect(adobeIndex).toBeGreaterThan(-1)
    expect(premiumIndex).toBeLessThan(beratungIndex)
    expect(beratungIndex).toBeLessThan(adobeIndex)
  })

  it('sorts expense services by most negative yearly total first', async () => {
    setup('viewer')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () =>
        HttpResponse.json({
          year: 2026,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-expense',
                  group_name: 'Betrieb',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 3,
                  active_years: [2026],
                  subtotal_cells: makeCells('-350.00'),
                  services: [
                    {
                      service_id: 'service-small-negative',
                      service_name: 'Klein',
                      partner_name: 'Lieferant A',
                      service_type: 'supplier',
                      erfolgsneutral: false,
                      cells: makeCells('-50.00'),
                    },
                    {
                      service_id: 'service-most-negative',
                      service_name: 'Groß',
                      partner_name: 'Lieferant B',
                      service_type: 'supplier',
                      erfolgsneutral: false,
                      cells: makeCells('-200.00'),
                    },
                    {
                      service_id: 'service-middle-negative',
                      service_name: 'Mittel',
                      partner_name: 'Lieferant C',
                      service_type: 'supplier',
                      erfolgsneutral: false,
                      cells: makeCells('-100.00'),
                    },
                  ],
                },
              ],
              totals: makeCells('-350.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Lieferant B / Groß')).toBeInTheDocument())

    const expenseSection = screen.getByRole('heading', { name: 'Ausgaben' }).closest('section')
    expect(expenseSection).not.toBeNull()
    const expenseRows = within(expenseSection as HTMLElement).getAllByRole('row')
    const expenseText = expenseRows.map((row) => row.textContent ?? '')
    const largestNegativeIndex = expenseText.findIndex((text) => text.includes('Lieferant B / Groß'))
    const middleNegativeIndex = expenseText.findIndex((text) => text.includes('Lieferant C / Mittel'))
    const smallestNegativeIndex = expenseText.findIndex((text) => text.includes('Lieferant A / Klein'))

    expect(largestNegativeIndex).toBeGreaterThan(-1)
    expect(middleNegativeIndex).toBeGreaterThan(-1)
    expect(smallestNegativeIndex).toBeGreaterThan(-1)
    expect(largestNegativeIndex).toBeLessThan(middleNegativeIndex)
    expect(middleNegativeIndex).toBeLessThan(smallestNegativeIndex)
  })

  it('shows a backend error when the matrix endpoint fails', async () => {
    setup('accountant')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () =>
        HttpResponse.json({ detail: 'DB migration missing' }, { status: 500 }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText(/Fehler beim Laden der Matrix/i)).toBeInTheDocument())
  })

  it('keeps empty groups visible for editing users', async () => {
    setup('accountant')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () =>
        HttpResponse.json({
          year: 2026,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-empty',
                  group_name: 'Neue Gruppe',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 0,
                  active_years: [],
                  subtotal_cells: makeCells('0.00'),
                  services: [],
                },
              ],
              totals: makeCells('0.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Neue Gruppe')).toBeInTheDocument())
    expect(screen.getAllByRole('button', { name: /gruppe anlegen/i }).length).toBeGreaterThan(0)
  })

  it('toggles all groups within a section at once', async () => {
    setup('viewer')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () =>
        HttpResponse.json({
          year: 2026,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-income-a',
                  group_name: 'A Gruppe',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [2026],
                  subtotal_cells: makeCells('100.00'),
                  services: [
                    {
                      service_id: 'service-income-a',
                      service_name: 'A Leistung',
                      partner_name: 'Alpha GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('100.00'),
                    },
                  ],
                },
                {
                  group_id: 'group-income-b',
                  group_name: 'B Gruppe',
                  sort_order: 2,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [2026],
                  subtotal_cells: makeCells('200.00'),
                  services: [
                    {
                      service_id: 'service-income-b',
                      service_name: 'B Leistung',
                      partner_name: 'Beta GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('200.00'),
                    },
                  ],
                },
              ],
              totals: makeCells('300.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Alpha GmbH / A Leistung')).toBeInTheDocument())
    expect(screen.getByText('Beta GmbH / B Leistung')).toBeInTheDocument()

    const incomeSection = screen.getByRole('heading', { name: 'Einnahmen' }).closest('section')
    if (!incomeSection) {
      throw new Error('Income section not found')
    }

    fireEvent.click(within(incomeSection).getByRole('button', { name: 'Alle zuklappen' }))

    expect(within(incomeSection).queryByText('Alpha GmbH / A Leistung')).not.toBeInTheDocument()
    expect(within(incomeSection).queryByText('Beta GmbH / B Leistung')).not.toBeInTheDocument()
    expect(within(incomeSection).getByRole('button', { name: 'Alle aufklappen' })).toBeInTheDocument()

    fireEvent.click(within(incomeSection).getByRole('button', { name: 'Alle aufklappen' }))

    expect(within(incomeSection).getByText('Alpha GmbH / A Leistung')).toBeInTheDocument()
    expect(within(incomeSection).getByText('Beta GmbH / B Leistung')).toBeInTheDocument()
  })

  it('lets editing users reorder groups via drag and drop', async () => {
    setup('accountant')

    const incomeGroups = [
      {
        group_id: 'group-a',
        group_name: 'Alpha',
        sort_order: 1,
        collapsed: false,
        assigned_service_count: 1,
        active_years: [2026],
        subtotal_cells: makeCells('100.00'),
        services: [
          {
            service_id: 'service-a',
            service_name: 'A Leistung',
            partner_name: 'Alpha GmbH',
            service_type: 'customer',
            erfolgsneutral: false,
            cells: makeCells('100.00'),
          },
        ],
      },
      {
        group_id: 'group-b',
        group_name: 'Beta',
        sort_order: 2,
        collapsed: false,
        assigned_service_count: 1,
        active_years: [2026],
        subtotal_cells: makeCells('200.00'),
        services: [
          {
            service_id: 'service-b',
            service_name: 'B Leistung',
            partner_name: 'Beta GmbH',
            service_type: 'customer',
            erfolgsneutral: false,
            cells: makeCells('200.00'),
          },
        ],
      },
      {
        group_id: 'group-c',
        group_name: 'Gamma',
        sort_order: 3,
        collapsed: false,
        assigned_service_count: 1,
        active_years: [2026],
        subtotal_cells: makeCells('300.00'),
        services: [
          {
            service_id: 'service-c',
            service_name: 'C Leistung',
            partner_name: 'Gamma GmbH',
            service_type: 'customer',
            erfolgsneutral: false,
            cells: makeCells('300.00'),
          },
        ],
      },
    ]

    const reorderRequests: Array<{ groupId: string; sortOrder: number | undefined }> = []

    function buildMatrixResponse() {
      return {
        year: 2026,
        base_currency: 'EUR',
        sections: {
          income: {
            currency: 'EUR',
            excluded_currency_count: 0,
            excluded_currency_amount_gross: '0.00',
            groups: [...incomeGroups].sort((left, right) => left.sort_order - right.sort_order),
            totals: makeCells('600.00'),
          },
          expense: {
            currency: 'EUR',
            excluded_currency_count: 0,
            excluded_currency_amount_gross: '0.00',
            groups: [],
            totals: makeCells('0.00'),
          },
          neutral: {
            currency: 'EUR',
            excluded_currency_count: 0,
            excluded_currency_amount_gross: '0.00',
            groups: [],
            totals: makeCells('0.00'),
          },
        },
      }
    }

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () => HttpResponse.json(buildMatrixResponse())),
      http.patch(`/api/v1/mandants/${MANDANT_ID}/service-groups/:groupId`, async ({ params, request }) => {
        const payload = await request.json() as { sort_order?: number }
        const group = incomeGroups.find((entry) => entry.group_id === params.groupId)
        if (!group) {
          return HttpResponse.json({ detail: 'not found' }, { status: 404 })
        }
        group.sort_order = payload.sort_order ?? group.sort_order
        reorderRequests.push({ groupId: String(params.groupId), sortOrder: payload.sort_order })
        return HttpResponse.json(group)
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument())

    const sourceRow = screen.getByText('Gamma').closest('tr')
    const targetRow = screen.getByText('Alpha').closest('tr')
    if (!sourceRow) {
      throw new Error('Source row for group reorder not found')
    }
    if (!targetRow) {
      throw new Error('Target row for group reorder not found')
    }

    const dataTransfer = createDataTransfer()
    fireEvent.dragStart(sourceRow, { dataTransfer })
    fireEvent.dragOver(targetRow, { dataTransfer })
    fireEvent.drop(targetRow, { dataTransfer })

    await waitFor(() => expect(reorderRequests.some((entry) => entry.groupId === 'group-c' && entry.sortOrder === 1)).toBe(true))

    await waitFor(() => {
      const gammaRow = screen.getByText('Gamma').closest('tr')
      const alphaRow = screen.getByText('Alpha').closest('tr')
      const betaRow = screen.getByText('Beta').closest('tr')
      if (!gammaRow || !alphaRow || !betaRow) {
        throw new Error('Expected group rows not found after reorder')
      }
      expect(gammaRow.compareDocumentPosition(alphaRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      expect(alphaRow.compareDocumentPosition(betaRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
  })

  it('lets editing users move services between groups via drag and drop', async () => {
    setup('accountant')

    const incomeGroups = [
      {
        group_id: 'group-source',
        group_name: 'Quelle',
        sort_order: 1,
        collapsed: false,
        assigned_service_count: 1,
        active_years: [2026],
        subtotal_cells: makeCells('100.00'),
        services: [
          {
            service_id: 'service-move',
            service_name: 'Verschieben',
            partner_name: 'Alpha GmbH',
            service_type: 'customer',
            erfolgsneutral: false,
            cells: makeCells('100.00'),
          },
        ],
      },
      {
        group_id: 'group-target',
        group_name: 'Ziel',
        sort_order: 2,
        collapsed: false,
        assigned_service_count: 0,
        active_years: [2026],
        subtotal_cells: makeCells('0.00'),
        services: [],
      },
    ]

    const assignmentRequests: Array<{ serviceId: string; groupId: string }> = []

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () => HttpResponse.json(
        buildIncomeMatrixResponse([...incomeGroups].sort((left, right) => left.sort_order - right.sort_order)),
      )),
      http.post(`/api/v1/mandants/${MANDANT_ID}/services/:serviceId/group-assignment`, async ({ params, request }) => {
        const payload = await request.json() as { service_group_id: string }
        const sourceGroup = incomeGroups.find((group) => group.services.some((service) => service.service_id === params.serviceId))
        const targetGroup = incomeGroups.find((group) => group.group_id === payload.service_group_id)
        if (!sourceGroup || !targetGroup) {
          return HttpResponse.json({ detail: 'not found' }, { status: 404 })
        }

        const serviceIndex = sourceGroup.services.findIndex((service) => service.service_id === params.serviceId)
        const [service] = sourceGroup.services.splice(serviceIndex, 1)
        if (!service) {
          return HttpResponse.json({ detail: 'service not found' }, { status: 404 })
        }
        targetGroup.services.push(service)
        sourceGroup.assigned_service_count = sourceGroup.services.length
        targetGroup.assigned_service_count = targetGroup.services.length
        sourceGroup.subtotal_cells = makeCells('0.00')
        targetGroup.subtotal_cells = makeCells('100.00')
        assignmentRequests.push({ serviceId: String(params.serviceId), groupId: payload.service_group_id })

        return HttpResponse.json({
          id: 'assignment-1',
          mandant_id: MANDANT_ID,
          service_id: String(params.serviceId),
          service_group_id: payload.service_group_id,
          created_at: '2026-04-16T00:00:00Z',
          updated_at: '2026-04-16T00:00:00Z',
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Alpha GmbH / Verschieben')).toBeInTheDocument())

    const sourceRow = screen.getByText('Alpha GmbH / Verschieben').closest('tr')
    const targetRow = screen.getByText('Ziel').closest('tr')
    if (!sourceRow) {
      throw new Error('Source row for service move not found')
    }
    if (!targetRow) {
      throw new Error('Target row for service move not found')
    }

    const dataTransfer = createDataTransfer()
    fireEvent.dragStart(sourceRow, { dataTransfer })
    fireEvent.dragOver(targetRow, { dataTransfer })
    fireEvent.drop(targetRow, { dataTransfer })

    await waitFor(() => expect(assignmentRequests).toContainEqual({ serviceId: 'service-move', groupId: 'group-target' }))
    await waitFor(() => {
      const targetGroupRow = screen.getByText('Ziel').closest('tr')
      const serviceRow = screen.getByText('Alpha GmbH / Verschieben').closest('tr')
      if (!targetGroupRow || !serviceRow) {
        throw new Error('Expected rows not found after service move')
      }
      expect(targetGroupRow.compareDocumentPosition(serviceRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
  })

  it('accepts service drops from text/plain fallback payloads', async () => {
    setup('accountant')

    const incomeGroups = [
      {
        group_id: 'group-source',
        group_name: 'Quelle',
        sort_order: 1,
        collapsed: false,
        assigned_service_count: 1,
        active_years: [2026],
        subtotal_cells: makeCells('100.00'),
        services: [
          {
            service_id: 'service-plain',
            service_name: 'Fallback',
            partner_name: 'Alpha GmbH',
            service_type: 'customer',
            erfolgsneutral: false,
            cells: makeCells('100.00'),
          },
        ],
      },
      {
        group_id: 'group-target',
        group_name: 'Ziel',
        sort_order: 2,
        collapsed: false,
        assigned_service_count: 0,
        active_years: [2026],
        subtotal_cells: makeCells('0.00'),
        services: [],
      },
    ]

    const assignmentRequests: Array<{ serviceId: string; groupId: string }> = []

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () => HttpResponse.json(
        buildIncomeMatrixResponse([...incomeGroups].sort((left, right) => left.sort_order - right.sort_order)),
      )),
      http.post(`/api/v1/mandants/${MANDANT_ID}/services/:serviceId/group-assignment`, async ({ params, request }) => {
        const payload = await request.json() as { service_group_id: string }
        assignmentRequests.push({ serviceId: String(params.serviceId), groupId: payload.service_group_id })
        return HttpResponse.json({
          id: 'assignment-plain',
          mandant_id: MANDANT_ID,
          service_id: String(params.serviceId),
          service_group_id: payload.service_group_id,
          created_at: '2026-04-16T00:00:00Z',
          updated_at: '2026-04-16T00:00:00Z',
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Ziel')).toBeInTheDocument())

    const targetRow = screen.getByText('Ziel').closest('tr')
    if (!targetRow) {
      throw new Error('Target row for plain-text service move not found')
    }

    const plainTextTransfer = {
      getData: (type: string) => type === 'text/plain' ? JSON.stringify({ serviceId: 'service-plain', section: 'income' }) : '',
    }

    fireEvent.dragOver(targetRow, { dataTransfer: plainTextTransfer })
    fireEvent.drop(targetRow, { dataTransfer: plainTextTransfer })

    await waitFor(() => expect(assignmentRequests).toContainEqual({ serviceId: 'service-plain', groupId: 'group-target' }))
  })

  it('blocks deleting a group that still has assigned services in other years', async () => {
    setup('accountant')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, () =>
        HttpResponse.json({
          year: 2026,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-archive',
                  group_name: 'Archivgruppe',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 2,
                  active_years: [2024, 2025],
                  subtotal_cells: makeCells('0.00'),
                  services: [],
                },
              ],
              totals: makeCells('0.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        }),
      ),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Archivgruppe')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Gruppe Archivgruppe löschen' }))

    await waitFor(() => expect(screen.getByText(/Diese Gruppe enthält noch 2 Services/i)).toBeInTheDocument())
    expect(screen.getByText(/In der aktuellen Jahresansicht sind keine Services sichtbar/i)).toBeInTheDocument()
    expect(screen.getByText(/2024, 2025/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Löschen' })).toBeDisabled()
  })

  it('allows year navigation only when adjacent years have data', async () => {
    setup('viewer')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2025, 2026] })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, ({ request }) => {
        const requestUrl = new URL(request.url)
        const requestedYear = Number(requestUrl.searchParams.get('year') ?? '2026')
        return HttpResponse.json({
          year: requestedYear,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: `group-${requestedYear}`,
                  group_name: `Gruppe ${requestedYear}`,
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [requestedYear],
                  subtotal_cells: makeCells('100.00'),
                  services: [
                    {
                      service_id: `service-${requestedYear}`,
                      service_name: `Leistung ${requestedYear}`,
                      partner_name: 'Beispiel GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('100.00'),
                    },
                  ],
                },
              ],
              totals: makeCells('100.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Gruppe 2026')).toBeInTheDocument())

    const previousYearButton = screen.getByRole('button', { name: '◀ Vorjahr' })
    const nextYearButton = screen.getByRole('button', { name: 'Folgejahr ▶' })

    expect(previousYearButton).toBeEnabled()
    expect(nextYearButton).toBeDisabled()

    fireEvent.click(previousYearButton)

    await waitFor(() => expect(screen.getByText('Gruppe 2025')).toBeInTheDocument())
    expect(screen.getByText('2025')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '◀ Vorjahr' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Folgejahr ▶' })).toBeEnabled()
  })

  it('shows a multi-year overview and allows switching back to the year view', async () => {
    setup('viewer')

    const requestedYears: number[] = []

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2024, 2025, 2026] })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, ({ request }) => {
        const requestUrl = new URL(request.url)
        const requestedYear = Number(requestUrl.searchParams.get('year') ?? '2026')
        requestedYears.push(requestedYear)

        return HttpResponse.json({
          year: requestedYear,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-growth',
                  group_name: 'Wachstum',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [2024, 2025, 2026],
                  subtotal_cells: makeCells(String((requestedYear - 2023) * 100)),
                  services: [
                    {
                      service_id: 'service-growth',
                      service_name: 'Jahresabo',
                      partner_name: 'Beispiel GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells(String((requestedYear - 2023) * 100)),
                    },
                  ],
                },
              ],
              totals: makeCells(String((requestedYear - 2023) * 100)),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Beispiel GmbH / Jahresabo')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Mehrjahresansicht' }))

    await waitFor(() => expect(screen.getByText('Mehrjahresansicht')).toBeInTheDocument())
    await waitFor(() => expect(new Set(requestedYears)).toEqual(new Set([2024, 2025, 2026])))
    expect(screen.getAllByText('2024').length).toBeGreaterThan(0)
    expect(screen.getAllByText('2025').length).toBeGreaterThan(0)
    expect(screen.getAllByText('2026').length).toBeGreaterThan(0)
    expect(screen.getByText('Wachstum')).toBeInTheDocument()
    expect(screen.getByText('Beispiel GmbH / Jahresabo')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zur Jahresansicht' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Mehrjahresansicht' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '◀ Vorjahr' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Folgejahr ▶' })).toBeDisabled()
  })

  it('supports drag and drop in the multi-year overview', async () => {
    setup('accountant')

    const incomeGroupsByYear = new Map<number, Array<Record<string, unknown>>>([
      [2025, [
        {
          group_id: 'group-source',
          group_name: 'Quelle',
          sort_order: 1,
          collapsed: false,
          assigned_service_count: 1,
          active_years: [2025, 2026],
          subtotal_cells: makeCells('100.00'),
          services: [
            {
              service_id: 'service-move',
              service_name: 'Mehrjahr',
              partner_name: 'Alpha GmbH',
              service_type: 'customer',
              erfolgsneutral: false,
              cells: makeCells('100.00'),
            },
          ],
        },
        {
          group_id: 'group-target',
          group_name: 'Ziel',
          sort_order: 2,
          collapsed: false,
          assigned_service_count: 0,
          active_years: [2025, 2026],
          subtotal_cells: makeCells('0.00'),
          services: [],
        },
      ]],
      [2026, [
        {
          group_id: 'group-source',
          group_name: 'Quelle',
          sort_order: 1,
          collapsed: false,
          assigned_service_count: 1,
          active_years: [2025, 2026],
          subtotal_cells: makeCells('200.00'),
          services: [
            {
              service_id: 'service-move',
              service_name: 'Mehrjahr',
              partner_name: 'Alpha GmbH',
              service_type: 'customer',
              erfolgsneutral: false,
              cells: makeCells('200.00'),
            },
          ],
        },
        {
          group_id: 'group-target',
          group_name: 'Ziel',
          sort_order: 2,
          collapsed: false,
          assigned_service_count: 0,
          active_years: [2025, 2026],
          subtotal_cells: makeCells('0.00'),
          services: [],
        },
      ]],
    ])
    const assignmentRequests: Array<{ serviceId: string; groupId: string }> = []

    function buildResponseForYear(year: number) {
      return {
        year,
        base_currency: 'EUR',
        sections: {
          income: {
            currency: 'EUR',
            excluded_currency_count: 0,
            excluded_currency_amount_gross: '0.00',
            groups: incomeGroupsByYear.get(year) ?? [],
            totals: makeCells(year === 2025 ? '100.00' : '200.00'),
          },
          expense: {
            currency: 'EUR',
            excluded_currency_count: 0,
            excluded_currency_amount_gross: '0.00',
            groups: [],
            totals: makeCells('0.00'),
          },
          neutral: {
            currency: 'EUR',
            excluded_currency_count: 0,
            excluded_currency_amount_gross: '0.00',
            groups: [],
            totals: makeCells('0.00'),
          },
        },
      }
    }

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2025, 2026] })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, ({ request }) => {
        const requestUrl = new URL(request.url)
        const requestedYear = Number(requestUrl.searchParams.get('year') ?? '2026')
        return HttpResponse.json(buildResponseForYear(requestedYear))
      }),
      http.post(`/api/v1/mandants/${MANDANT_ID}/services/:serviceId/group-assignment`, async ({ params, request }) => {
        const payload = await request.json() as { service_group_id: string }
        assignmentRequests.push({ serviceId: String(params.serviceId), groupId: payload.service_group_id })

        for (const groups of incomeGroupsByYear.values()) {
          const sourceGroup = groups.find((group) => Array.isArray(group.services) && group.services.some((service) => service.service_id === params.serviceId))
          const targetGroup = groups.find((group) => group.group_id === payload.service_group_id)
          if (!sourceGroup || !targetGroup || !Array.isArray(sourceGroup.services) || !Array.isArray(targetGroup.services)) {
            continue
          }

          const serviceIndex = sourceGroup.services.findIndex((service) => service.service_id === params.serviceId)
          const [service] = sourceGroup.services.splice(serviceIndex, 1)
          if (!service) {
            continue
          }
          targetGroup.services.push(service)
          sourceGroup.assigned_service_count = sourceGroup.services.length
          targetGroup.assigned_service_count = targetGroup.services.length
          sourceGroup.subtotal_cells = makeCells('0.00')
          targetGroup.subtotal_cells = makeCells(service.cells.year_total.net)
        }

        return HttpResponse.json({
          id: 'assignment-multi',
          mandant_id: MANDANT_ID,
          service_id: String(params.serviceId),
          service_group_id: payload.service_group_id,
          created_at: '2026-04-19T00:00:00Z',
          updated_at: '2026-04-19T00:00:00Z',
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Alpha GmbH / Mehrjahr')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Mehrjahresansicht' }))

    await waitFor(() => expect(screen.getByText('Ziel')).toBeInTheDocument())

    const sourceRow = screen.getByText('Alpha GmbH / Mehrjahr').closest('tr')
    const targetRow = screen.getByText('Ziel').closest('tr')
    if (!sourceRow) {
      throw new Error('Source row for multi-year service move not found')
    }
    if (!targetRow) {
      throw new Error('Target row for multi-year service move not found')
    }

    const dataTransfer = createDataTransfer()
    fireEvent.dragStart(sourceRow, { dataTransfer })
    fireEvent.dragOver(targetRow, { dataTransfer })
    fireEvent.drop(targetRow, { dataTransfer })

    await waitFor(() => expect(assignmentRequests).toContainEqual({ serviceId: 'service-move', groupId: 'group-target' }))
    await waitFor(() => {
      const targetGroupRow = screen.getByText('Ziel').closest('tr')
      const serviceRow = screen.getByText('Alpha GmbH / Mehrjahr').closest('tr')
      if (!targetGroupRow || !serviceRow) {
        throw new Error('Expected rows not found after multi-year service move')
      }
      expect(targetGroupRow.compareDocumentPosition(serviceRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
  })

  it('keeps collapsed group state when switching years', async () => {
    setup('viewer')

    server.use(
      http.get(`/api/v1/mandants/${MANDANT_ID}/journal/years`, () => HttpResponse.json({ years: [2025, 2026] })),
      http.get(`/api/v1/mandants/${MANDANT_ID}/reports/income-expense`, ({ request }) => {
        const requestUrl = new URL(request.url)
        const requestedYear = Number(requestUrl.searchParams.get('year') ?? '2026')
        return HttpResponse.json({
          year: requestedYear,
          base_currency: 'EUR',
          sections: {
            income: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [
                {
                  group_id: 'group-recurring',
                  group_name: 'Wiederkehrend',
                  sort_order: 1,
                  collapsed: false,
                  assigned_service_count: 1,
                  active_years: [2025, 2026],
                  subtotal_cells: makeCells('100.00'),
                  services: [
                    {
                      service_id: `service-${requestedYear}`,
                      service_name: `Leistung ${requestedYear}`,
                      partner_name: 'Beispiel GmbH',
                      service_type: 'customer',
                      erfolgsneutral: false,
                      cells: makeCells('100.00'),
                    },
                  ],
                },
              ],
              totals: makeCells('100.00'),
            },
            expense: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
            neutral: {
              currency: 'EUR',
              excluded_currency_count: 0,
              excluded_currency_amount_gross: '0.00',
              groups: [],
              totals: makeCells('0.00'),
            },
          },
        })
      }),
    )

    await act(async () => {
      renderPage()
    })

    await waitFor(() => expect(screen.getByText('Beispiel GmbH / Leistung 2026')).toBeInTheDocument())

    const incomeSection = screen.getByRole('heading', { name: 'Einnahmen' }).closest('section')
    if (!incomeSection) {
      throw new Error('Income section not found')
    }

    fireEvent.click(within(incomeSection).getByRole('button', { name: '▼' }))
    expect(within(incomeSection).queryByText('Beispiel GmbH / Leistung 2026')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '◀ Vorjahr' }))

    await waitFor(() => expect(screen.getByText('2025')).toBeInTheDocument())
    const updatedIncomeHeading = await screen.findByRole('heading', { name: 'Einnahmen' })
    const updatedIncomeSection = updatedIncomeHeading.closest('section')
    if (!updatedIncomeSection) {
      throw new Error('Updated income section not found')
    }

    expect(within(updatedIncomeSection).queryByText('Beispiel GmbH / Leistung 2025')).not.toBeInTheDocument()
    expect(within(updatedIncomeSection).getByRole('button', { name: '▶' })).toBeInTheDocument()
  })
})