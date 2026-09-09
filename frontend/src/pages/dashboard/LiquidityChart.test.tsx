import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { LiquidityResponse } from '@/api/journal'
import { LiquidityChart } from './LiquidityChart'
import { buildChartGeometry, formatPeriod } from './liquidity-chart-geometry'

function month(
  period: string,
  closing: string,
  inflow = '1000.00',
  outflow = '-4000.00',
  band?: { low: string; high: string },
) {
  return {
    period,
    opening_balance: '0.00',
    inflow,
    outflow,
    net: '0.00',
    closing_balance: closing,
    closing_low: band?.low ?? closing,
    closing_high: band?.high ?? closing,
  }
}

/** Punkt ohne Unsicherheitsband — Band-Kanten liegen auf dem Wert. */
function point(label: string, value: number) {
  return { label, value, low: value, high: value, detail: null }
}

function response(overrides: Partial<LiquidityResponse> = {}): LiquidityResponse {
  return {
    currency: 'EUR',
    start_balance: '5000.00',
    as_of: '2026-08-31',
    months: [month('2026-09', '2000.00'), month('2026-10', '-1000.00')],
    lowest_balance: '-1000.00',
    lowest_period: '2026-10',
    lowest_balance_low: '-1000.00',
    uncovered_average_per_month: '0.00',
    ...overrides,
  }
}

describe('formatPeriod', () => {
  it('kürzt Perioden auf Monat und Jahr', () => {
    expect(formatPeriod('2026-09')).toBe('Sep 26')
    expect(formatPeriod('2027-12')).toBe('Dez 27')
  })

  it('gibt Unbekanntes unverändert zurück', () => {
    expect(formatPeriod('kaputt')).toBe('kaputt')
  })
})

describe('buildChartGeometry', () => {
  const points = [point('jetzt', 5000), point('Sep 26', 2000), point('Okt 26', -1000)]

  it('spannt die Skala über Null hinweg auf', () => {
    const geometry = buildChartGeometry(points)

    expect(geometry.yMin).toBeLessThan(-1000)
    expect(geometry.yMax).toBeGreaterThan(5000)
  })

  it('bildet höhere Werte weiter oben ab', () => {
    const geometry = buildChartGeometry(points)

    expect(geometry.y(5000)).toBeLessThan(geometry.y(2000))
    expect(geometry.y(2000)).toBeLessThan(geometry.y(-1000))
  })

  it('legt die Nulllinie zwischen positive und negative Werte', () => {
    const geometry = buildChartGeometry(points)

    expect(geometry.zeroY).toBeGreaterThan(geometry.y(2000))
    expect(geometry.zeroY).toBeLessThan(geometry.y(-1000))
  })

  it('verteilt die Punkte über die Breite', () => {
    const geometry = buildChartGeometry(points)

    expect(geometry.x(0)).toBeLessThan(geometry.x(1))
    expect(geometry.x(1)).toBeLessThan(geometry.x(2))
  })

  it('kommt mit einer konstanten Reihe ohne Division durch Null zurecht', () => {
    const geometry = buildChartGeometry([point('a', 0), point('b', 0)])

    expect(Number.isFinite(geometry.zeroY)).toBe(true)
    expect(Number.isFinite(geometry.y(0))).toBe(true)
  })

  it('liefert ohne Bandbreite keinen Bandpfad', () => {
    expect(buildChartGeometry(points).band).toBeNull()
  })

  it('spannt die Skala über die Bandkanten, nicht nur über die Linie', () => {
    const geometry = buildChartGeometry([
      { label: 'jetzt', value: 0, low: 0, high: 0, detail: null },
      { label: 'Sep 26', value: 1000, low: -8000, high: 10000, detail: null },
    ])

    expect(geometry.yMin).toBeLessThanOrEqual(-8000)
    expect(geometry.yMax).toBeGreaterThanOrEqual(10000)
    expect(geometry.band).toContain('Z')
  })
})

describe('LiquidityChart', () => {
  it('nennt den Tiefstand und warnt bei Unterdeckung', () => {
    render(<LiquidityChart data={response()} />)

    expect(screen.getByText('-1.000,00 €')).toBeInTheDocument()
    expect(screen.getByText(/Deckung reicht nicht/)).toBeInTheDocument()
  })

  it('meldet einen durchgehend positiven Verlauf', () => {
    render(
      <LiquidityChart
        data={response({
          months: [month('2026-09', '4000.00')],
          lowest_balance: '4000.00',
          lowest_period: '2026-09',
          lowest_balance_low: '4000.00',
        })}
      />,
    )

    expect(screen.getByText(/bleibt über den gesamten Horizont positiv/)).toBeInTheDocument()
  })

  it('weist bei vorhandenem Band den unguenstigen Verlauf aus', () => {
    render(
      <LiquidityChart
        data={response({
          months: [
            month('2026-09', '2000.00', '1000.00', '-4000.00', {
              low: '-500.00',
              high: '4500.00',
            }),
          ],
          lowest_balance: '2000.00',
          lowest_period: '2026-09',
          lowest_balance_low: '-500.00',
        })}
      />,
    )

    expect(screen.getByText('Ungünstiger Verlauf')).toBeInTheDocument()
    expect(screen.getByText('-500,00 €')).toBeInTheDocument()
    expect(screen.getByText(/graue Band ist die Unsicherheit/)).toBeInTheDocument()
  })

  it('nennt ohne Band keinen unguenstigen Verlauf', () => {
    render(<LiquidityChart data={response()} />)

    expect(screen.queryByText('Ungünstiger Verlauf')).not.toBeInTheDocument()
  })

  it('blendet die Zahlen auf Wunsch als Tabelle ein', async () => {
    render(<LiquidityChart data={response()} />)

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Zahlen anzeigen' }))

    const table = screen.getByRole('table')
    expect(table).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Okt 26/ })).toBeInTheDocument()
  })

  it('weist nicht abgedeckte Buchungen aus', () => {
    render(<LiquidityChart data={response({ uncovered_average_per_month: '-1211.09' })} />)

    expect(screen.getByText(/Nicht enthalten: rund -1.211,09/)).toBeInTheDocument()
  })

  it('verschweigt den Hinweis, wenn alles abgedeckt ist', () => {
    render(<LiquidityChart data={response({ uncovered_average_per_month: '0.00' })} />)

    expect(screen.queryByText(/Nicht enthalten/)).not.toBeInTheDocument()
  })

  it('zeigt einen Hinweis, wenn keine Prognose möglich ist', () => {
    render(<LiquidityChart data={response({ months: [] })} />)

    expect(screen.getByText(/Noch keine Prognose möglich/)).toBeInTheDocument()
  })

  it('beschreibt die Grafik für Screenreader', () => {
    render(<LiquidityChart data={response()} />)

    expect(screen.getByRole('img')).toHaveAccessibleName(/Tiefstand -1\.000,00 €/)
  })
})
