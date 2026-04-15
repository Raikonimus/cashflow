import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { vi } from 'vitest'
import { ImportPage } from './ImportPage'
import { useAuthStore } from '@/store/auth-store'

const uploadCsvMock = vi.fn()
const listImportRunsMock = vi.fn()
const listAccountsMock = vi.fn()

vi.mock('@/api/imports', () => ({
  uploadCsv: (...args: unknown[]) => uploadCsvMock(...args),
  listImportRuns: (...args: unknown[]) => listImportRunsMock(...args),
}))

vi.mock('@/api/accounts', async () => {
  const actual = await vi.importActual<typeof import('@/api/accounts')>('@/api/accounts')
  return {
    ...actual,
    listAccounts: (...args: unknown[]) => listAccountsMock(...args),
  }
})

function renderImportPage(initialPath = '/accounts/account-1/import') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      { path: '/accounts/:accountId/import', element: <ImportPage /> },
      { path: '/accounts/:accountId', element: <div>Account Page</div> },
      { path: '/accounts', element: <div>Accounts Page</div> },
    ],
    { initialEntries: [initialPath] },
  )

  return {
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

describe('ImportPage', () => {
  beforeEach(() => {
    uploadCsvMock.mockReset()
    listImportRunsMock.mockReset()
    listAccountsMock.mockReset()

    useAuthStore.setState({
      token: 'mock-token',
      user: { sub: 'user-1', role: 'accountant', mandant_id: 'mandant-1' },
    })

    listAccountsMock.mockResolvedValue([
      {
        id: 'account-1',
        mandant_id: 'mandant-1',
        name: 'Testkonto',
        iban: null,
        currency: 'EUR',
        is_active: true,
        created_at: '2026-04-01T00:00:00',
        updated_at: '2026-04-01T00:00:00',
        has_column_mapping: true,
      },
    ])
    listImportRunsMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 20, pages: 0 })
  })

  it('shows detailed error message when upload fails', async () => {
    uploadCsvMock.mockRejectedValue(
      new AxiosError(
        'Request failed with status code 422',
        'ERR_BAD_REQUEST',
        undefined,
        undefined,
        {
          data: { detail: 'CSV is missing duplicate-check columns: Referenz, Externe ID' },
          status: 422,
          statusText: 'Unprocessable Entity',
          headers: {},
          config: { headers: {} as never },
        },
      ),
    )

    const { container } = renderImportPage()

    await waitFor(() => {
      expect(screen.getByText(/csv-import/i)).toBeInTheDocument()
    })

    const file = new File(['a,b\n1,2'], 'test.csv', { type: 'text/csv' })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).not.toBeNull()

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } })
    })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /importieren/i }))
    })

    await waitFor(() => {
      expect(
        screen.getByText(/csv is missing duplicate-check columns: referenz, externe id/i),
      ).toBeInTheDocument()
    })
  })

  it('shows a server unavailable message when no response is returned', async () => {
    uploadCsvMock.mockRejectedValue(new AxiosError('Network Error', 'ERR_NETWORK'))

    const { container } = renderImportPage()

    await waitFor(() => {
      expect(screen.getByText(/csv-import/i)).toBeInTheDocument()
    })

    const file = new File(['a,b\n1,2'], 'test.csv', { type: 'text/csv' })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).not.toBeNull()

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } })
    })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /importieren/i }))
    })

    await waitFor(() => {
      expect(
        screen.getByText(/der server ist nicht erreichbar\. bitte prüfen sie, ob backend und api laufen\./i),
      ).toBeInTheDocument()
    })
  })

  it('shows plain text error bodies from the server', async () => {
    uploadCsvMock.mockRejectedValue(
      new AxiosError(
        'Request failed with status code 500',
        'ERR_BAD_RESPONSE',
        undefined,
        undefined,
        {
          data: 'Import backend failed while reading multipart body',
          status: 500,
          statusText: 'Internal Server Error',
          headers: {},
          config: { headers: {} as never },
        },
      ),
    )

    const { container } = renderImportPage()

    await waitFor(() => {
      expect(screen.getByText(/csv-import/i)).toBeInTheDocument()
    })

    const file = new File(['a,b\n1,2'], 'test.csv', { type: 'text/csv' })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).not.toBeNull()

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } })
    })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /importieren/i }))
    })

    await waitFor(() => {
      expect(
        screen.getByText(/import backend failed while reading multipart body/i),
      ).toBeInTheDocument()
    })
  })
})