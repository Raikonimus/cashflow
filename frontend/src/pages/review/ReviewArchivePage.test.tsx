/// <reference types="vitest" />
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/store/auth-store'
import { ReviewArchivePage } from './ReviewArchivePage'

const mockListReviewArchive = vi.fn()

vi.mock('@/api/review', () => ({
  listReviewArchive: (...args: unknown[]) => mockListReviewArchive(...args),
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
        <ReviewArchivePage />
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
  mockListReviewArchive.mockResolvedValue({
    items: [
      {
        id: 'arch-1',
        mandant_id: MANDANT_ID,
        item_type: 'service_assignment',
        journal_line_id: 'line-1',
        service_id: null,
        context: { reason: 'single_match' },
        status: 'confirmed',
        created_at: '2025-03-01T00:00:00Z',
        updated_at: '2025-03-02T00:00:00Z',
        resolved_by: 'user-1',
        resolved_at: '2025-03-02T12:00:00Z',
        journal_line: {
          id: 'line-1', partner_id: 'partner-1', service_id: 'service-1', service_assignment_mode: 'manual', valuta_date: '2025-03-01', booking_date: '2025-03-01', amount: '-50.00', currency: 'EUR', text: 'Hosting April', partner_name_raw: 'Amazon EU',
        },
        service: null,
        assigned_journal_lines: [],
      },
    ],
    total: 1,
    page: 1,
    size: 100,
    pages: 1,
  })
})

describe('ReviewArchivePage', () => {
  it('renders archive entries', async () => {
    setupUser()
    await act(async () => {
      renderPage()
    })
    await waitFor(() => expect(mockListReviewArchive).toHaveBeenCalledWith(MANDANT_ID, {
      itemType: undefined,
      resolvedByUserId: undefined,
      resolvedFrom: undefined,
      resolvedTo: undefined,
      size: 100,
    }))
    expect(await screen.findByText(/hosting april/i)).toBeInTheDocument()
    expect(screen.getAllByText(/bestätigt/i).length).toBeGreaterThan(0)
  })

  it('sends filters to archive endpoint', async () => {
    setupUser()
    mockListReviewArchive.mockResolvedValue({ items: [], total: 0, page: 1, size: 100, pages: 1 })
    await act(async () => {
      renderPage()
    })
    await waitFor(() => screen.getByText(/kein archivtreffer/i))
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/typ/i), { target: { value: 'service_type_review' } })
      fireEvent.change(screen.getByPlaceholderText('UUID'), { target: { value: 'user-1' } })
    })
    await waitFor(() => expect(mockListReviewArchive).toHaveBeenLastCalledWith(MANDANT_ID, {
      itemType: 'service_type_review',
      resolvedByUserId: 'user-1',
      resolvedFrom: undefined,
      resolvedTo: undefined,
      size: 100,
    }))
  })
})