import { act, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/store/auth-store'
import { DashboardPage } from './DashboardPage'

const MANDANT_ID = 'mandant-1'

function cellText(cell: HTMLElement): string {
  return (cell.textContent ?? '').replace(/\s+/g, ' ')
}
const BALANCES_URL = `/api/v1/mandants/${MANDANT_ID}/reports/account-balances`
const LIQUIDITY_URL = `/api/v1/mandants/${MANDANT_ID}/reports/liquidity`

const EMPTY_LIQUIDITY = {
  currency: 'EUR',
  start_balance: '0.00',
  as_of: null,
  months: [],
  lowest_balance: '0.00',
  lowest_period: null,
  uncovered_average_per_month: '0.00',
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
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mockBalances(body: unknown, liquidity: unknown = EMPTY_LIQUIDITY) {
  server.use(
    http.get(BALANCES_URL, () => HttpResponse.json(body)),
    http.get(LIQUIDITY_URL, () => HttpResponse.json(liquidity)),
  )
}

describe('DashboardPage', () => {
  beforeEach(() => setup())

  it('zeigt Startsaldo, Buchungen und Kontostand je Konto', async () => {
    mockBalances({
      accounts: [
        {
          account_id: 'acc-1',
          account_name: 'Girokonto',
          iban: null,
          currency: 'EUR',
          is_active: true,
          opening_balance: '1500.00',
          booked_amount: '149.50',
          current_balance: '1649.50',
          line_count: 2,
          last_booking_date: '2025-04-15',
          foreign_currency_line_count: 0,
        },
      ],
      totals: [
        {
          currency: 'EUR',
          account_count: 1,
          opening_balance: '1500.00',
          booked_amount: '149.50',
          current_balance: '1649.50',
        },
      ],
    })

    renderPage()

    const row = await screen.findByRole('row', { name: /Girokonto/ })
    const cells = within(row).getAllByRole('cell')
    expect(cellText(cells[1])).toBe('1.500,00 €')
    expect(cellText(cells[2])).toBe('149,50 €')
    expect(cellText(cells[3])).toBe('1.649,50 €')
    expect(cellText(cells[4])).toBe('15.04.2025')
  })

  it('zeigt eine Gesamtsumme je Währung', async () => {
    mockBalances({
      accounts: [
        {
          account_id: 'acc-1',
          account_name: 'EUR-Konto',
          iban: null,
          currency: 'EUR',
          is_active: true,
          opening_balance: '0.00',
          booked_amount: '100.00',
          current_balance: '100.00',
          line_count: 1,
          last_booking_date: '2025-01-15',
          foreign_currency_line_count: 0,
        },
        {
          account_id: 'acc-2',
          account_name: 'USD-Konto',
          iban: null,
          currency: 'USD',
          is_active: true,
          opening_balance: '50.00',
          booked_amount: '0.00',
          current_balance: '50.00',
          line_count: 0,
          last_booking_date: null,
          foreign_currency_line_count: 0,
        },
      ],
      totals: [
        {
          currency: 'EUR',
          account_count: 1,
          opening_balance: '0.00',
          booked_amount: '100.00',
          current_balance: '100.00',
        },
        {
          currency: 'USD',
          account_count: 1,
          opening_balance: '50.00',
          booked_amount: '0.00',
          current_balance: '50.00',
        },
      ],
    })

    renderPage()

    expect(await screen.findByText(/Gesamt EUR/)).toBeInTheDocument()
    expect(screen.getByText(/Gesamt USD/)).toBeInTheDocument()
  })

  it('markiert negative Kontostände', async () => {
    mockBalances({
      accounts: [
        {
          account_id: 'acc-1',
          account_name: 'Kreditkarte',
          iban: null,
          currency: 'EUR',
          is_active: true,
          opening_balance: '-20.00',
          booked_amount: '-300.00',
          current_balance: '-320.00',
          line_count: 1,
          last_booking_date: '2025-02-01',
          foreign_currency_line_count: 0,
        },
      ],
      totals: [
        {
          currency: 'EUR',
          account_count: 1,
          opening_balance: '-20.00',
          booked_amount: '-300.00',
          current_balance: '-320.00',
        },
      ],
    })

    renderPage()

    const row = await screen.findByRole('row', { name: /Kreditkarte/ })
    const balanceCell = within(row).getAllByRole('cell')[3]
    expect(cellText(balanceCell)).toBe('-320,00 €')
    expect(balanceCell).toHaveClass('text-red-600')
  })

  it('warnt bei nicht berücksichtigten Fremdwährungsbuchungen', async () => {
    mockBalances({
      accounts: [
        {
          account_id: 'acc-1',
          account_name: 'Girokonto',
          iban: null,
          currency: 'EUR',
          is_active: true,
          opening_balance: '0.00',
          booked_amount: '100.00',
          current_balance: '100.00',
          line_count: 1,
          last_booking_date: '2025-01-15',
          foreign_currency_line_count: 2,
        },
      ],
      totals: [
        {
          currency: 'EUR',
          account_count: 1,
          opening_balance: '0.00',
          booked_amount: '100.00',
          current_balance: '100.00',
        },
      ],
    })

    renderPage()

    expect(
      await screen.findByText(/2 Buchungen in anderer Währung nicht berücksichtigt/),
    ).toBeInTheDocument()
  })

  it('zeigt einen Hinweis, wenn keine Konten vorhanden sind', async () => {
    mockBalances({ accounts: [], totals: [] })

    renderPage()

    expect(await screen.findByText(/Noch keine Konten vorhanden/)).toBeInTheDocument()
  })

  it('zeigt eine Fehlermeldung, wenn der Report fehlschlägt', async () => {
    server.use(
      http.get(BALANCES_URL, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
      http.get(LIQUIDITY_URL, () => HttpResponse.json(EMPTY_LIQUIDITY)),
    )

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/Fehler beim Laden der Kontostände/)).toBeInTheDocument(),
    )
  })

  it('zeigt die Liquiditätsvorschau unter den Kontoständen', async () => {
    mockBalances(
      {
        accounts: [
          {
            account_id: 'acc-1',
            account_name: 'Girokonto',
            iban: null,
            currency: 'EUR',
            is_active: true,
            opening_balance: '0.00',
            booked_amount: '5000.00',
            current_balance: '5000.00',
            line_count: 4,
            last_booking_date: '2026-08-31',
            foreign_currency_line_count: 0,
          },
        ],
        totals: [
          {
            currency: 'EUR',
            account_count: 1,
            opening_balance: '0.00',
            booked_amount: '5000.00',
            current_balance: '5000.00',
          },
        ],
      },
      {
        currency: 'EUR',
        start_balance: '5000.00',
        as_of: '2026-08-31',
        months: [
          {
            period: '2026-09',
            opening_balance: '5000.00',
            inflow: '1000.00',
            outflow: '-4000.00',
            net: '-3000.00',
            closing_balance: '2000.00',
          },
          {
            period: '2026-10',
            opening_balance: '2000.00',
            inflow: '1000.00',
            outflow: '-4000.00',
            net: '-3000.00',
            closing_balance: '-1000.00',
          },
        ],
        lowest_balance: '-1000.00',
        lowest_period: '2026-10',
        uncovered_average_per_month: '0.00',
      },
    )

    renderPage()

    expect(await screen.findByText('Liquiditätsvorschau')).toBeInTheDocument()
    expect(screen.getByText(/Deckung reicht nicht/)).toBeInTheDocument()
    expect(screen.getByText('-1.000,00 €')).toBeInTheDocument()
  })
})
