/// <reference types="vitest" />
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/store/auth-store'
import { ServiceTypeReviewPage } from './ServiceTypeReviewPage'

const mockListReviewItems = vi.fn()
const mockGetReviewItem = vi.fn()
const mockConfirmReviewItem = vi.fn()
const mockAdjustReviewItem = vi.fn()

vi.mock('@/api/review', () => ({
  listReviewItems: (...args: unknown[]) => mockListReviewItems(...args),
  getReviewItem: (...args: unknown[]) => mockGetReviewItem(...args),
  confirmReviewItem: (...args: unknown[]) => mockConfirmReviewItem(...args),
  adjustReviewItem: (...args: unknown[]) => mockAdjustReviewItem(...args),
}))

const MANDANT_ID = 'mandant-1'

function setupUser() {
  act(() => {
    useAuthStore.setState({
      token: 'tok',
      user: { sub: 'u1', role: 'accountant', mandant_id: MANDANT_ID },
      selectedMandant: { id: MANDANT_ID, name: 'Test' },
      mandants: [],
    })
  })
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ServiceTypeReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.clearAllMocks()
  act(() => {
    useAuthStore.setState({ token: null, user: null, selectedMandant: null, mandants: [] })
  })
})

beforeEach(() => {
  mockListReviewItems.mockResolvedValue({ items: [ITEM], total: 1, page: 1, size: 100, pages: 1 })
  mockGetReviewItem.mockResolvedValue(ITEM)
  mockConfirmReviewItem.mockResolvedValue({ ...ITEM, status: 'confirmed' })
  mockAdjustReviewItem.mockResolvedValue({ ...ITEM, status: 'adjusted' })
})

const ITEM = {
  id: 'item-3',
  mandant_id: MANDANT_ID,
  item_type: 'service_type_review',
  journal_line_id: null,
  service_id: 'service-payroll',
  context: { previous_type: 'unknown', auto_assigned_type: 'employee', reason: 'keyword:lohn' },
  status: 'open',
  created_at: '2025-03-01T00:00:00Z',
  updated_at: '2025-03-01T00:00:00Z',
  resolved_by: null,
  resolved_at: null,
  journal_line: null,
  service: {
    id: 'service-payroll',
    partner_id: 'partner-2',
    name: 'Lohnlauf',
    service_type: 'employee',
    tax_rate: '0.00',
    valid_from: null,
    valid_to: null,
    service_type_manual: false,
    tax_rate_manual: false,
  },
  assigned_journal_lines: [
    {
      id: 'line-a',
      partner_id: 'partner-2',
      service_id: 'service-payroll',
      service_assignment_mode: 'auto',
      valuta_date: '2025-03-31',
      booking_date: '2025-03-31',
      amount: '-1500.00',
      currency: 'EUR',
      text: 'Lohn März',
      partner_name_raw: 'Payroll GmbH',
    },
  ],
}

describe('ServiceTypeReviewPage', () => {
  it('renders type review list and detail', async () => {
    setupUser()
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(screen.getByText(/leistungstyp-prüfungen/i)).toBeInTheDocument())
    await waitFor(() => expect(mockListReviewItems).toHaveBeenCalledWith(MANDANT_ID, { status: 'open', itemType: 'service_type_review', size: 100 }))
    await waitFor(() => expect(mockGetReviewItem).toHaveBeenCalledWith(MANDANT_ID, 'item-3'))
    expect(screen.getAllByText('Lohnlauf').length).toBeGreaterThan(0)
    expect(await screen.findByText(/Lohn März/i)).toBeInTheDocument()
  })

  it('submits correction', async () => {
    setupUser()
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(mockGetReviewItem).toHaveBeenCalledWith(MANDANT_ID, 'item-3'))
    await screen.findByRole('heading', { name: 'Lohnlauf' })
    await act(async () => {
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'authority' } })
      fireEvent.click(screen.getByRole('button', { name: 'Korrigieren' }))
    })
    await waitFor(() => expect(screen.getByText(/wurde korrigiert/i)).toBeInTheDocument())
    expect(mockAdjustReviewItem).toHaveBeenCalledWith(MANDANT_ID, 'item-3', { service_type: 'authority', tax_rate: '0.00' })
  })
})