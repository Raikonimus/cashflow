import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { MandantsPage } from './MandantsPage'

const MANDANTS = [
  { id: 'm1', name: 'Alpha GmbH', is_active: true, created_at: '2026-01-01T00:00:00Z' },
]

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MandantsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MandantsPage', () => {
  it('shows cleanup preview in tenant configuration', async () => {
    server.use(
      http.get('/api/v1/mandants', () => HttpResponse.json(MANDANTS)),
      http.get('/api/v1/mandants/m1/cleanup-preview', () =>
        HttpResponse.json({
          mandant_id: 'm1',
          mandant_name: 'Alpha GmbH',
          delete_mandant: {
            key: 'delete_mandant',
            label: 'Mandant löschen',
            description: 'alles',
            items: [{ key: 'mandant', label: 'Mandant', count: 1 }],
          },
          delete_data: {
            key: 'delete_data',
            label: 'Nur alle Daten dieses Mandanten löschen',
            description: 'daten',
            items: [{ key: 'journal_lines_all', label: 'Buchungszeilen', count: 12 }],
          },
          selectable_sections: [
            {
              key: 'journal_data',
              label: 'Journaldaten',
              description: 'journal',
              items: [{ key: 'journal_lines', label: 'Buchungszeilen', count: 12 }],
            },
          ],
        }),
      ),
    )

    renderPage()

    await waitFor(() => expect(screen.getByText('Alpha GmbH')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Konfiguration' }))

    await waitFor(() => expect(screen.getByText('Mandantendetail-Konfiguration')).toBeInTheDocument())
    expect(screen.getByText('Mandant löschen')).toBeInTheDocument()
    expect(screen.getByText('Nur alle Daten dieses Mandanten löschen')).toBeInTheDocument()
    expect(screen.getAllByText('Buchungszeilen: 12')).toHaveLength(2)
  })
})