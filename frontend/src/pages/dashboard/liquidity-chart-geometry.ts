import type { LiquidityResponse } from '@/api/journal'

/** Skala und Pfade der Liquiditätskurve — ohne React, damit die Geometrie testbar bleibt. */

export const WIDTH = 800
export const HEIGHT = 260
export const PAD_LEFT = 68
export const PAD_RIGHT = 16
export const PAD_TOP = 16
export const PAD_BOTTOM = 30
export const INNER_WIDTH = WIDTH - PAD_LEFT - PAD_RIGHT
export const INNER_HEIGHT = HEIGHT - PAD_TOP - PAD_BOTTOM

const MONTH_ABBR = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export interface ChartPoint {
  label: string
  value: number
  /** Untere und obere Kante des Unsicherheitsbands; ohne Band gleich `value`. */
  low: number
  high: number
  detail: LiquidityResponse['months'][number] | null
}

export function parseAmount(value: string): number {
  const numeric = Number.parseFloat(value)
  return Number.isNaN(numeric) ? 0 : numeric
}

export function formatPeriod(period: string): string {
  const [year, month] = period.split('-')
  const index = Number.parseInt(month ?? '', 10) - 1
  if (!year || Number.isNaN(index) || index < 0 || index > 11) return period
  return `${MONTH_ABBR[index]} ${year.slice(2)}`
}

export function formatMoney(value: number, currency: string): string {
  const formatted = value.toLocaleString('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return `${formatted} ${currency === 'EUR' ? '\u20ac' : currency}`
}

export function formatAxis(value: number): string {
  return Math.round(value).toLocaleString('de-DE', { maximumFractionDigits: 0 })
}

const TARGET_TICKS = 4

/** Rundet eine Schrittweite auf 1/2/2,5/5 × 10^n — so werden Achsenwerte lesbar. */
export function niceStep(rough: number): number {
  if (!Number.isFinite(rough) || rough <= 0) return 1
  const exponent = Math.floor(Math.log10(rough))
  const base = 10 ** exponent
  const fraction = rough / base
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10
  return nice * base
}

export function buildChartGeometry(points: ChartPoint[]) {
  // Die Skala muss das Band fassen, sonst würde es am Rand abgeschnitten.
  const rawMin = Math.min(0, ...points.map((point) => Math.min(point.value, point.low)))
  const rawMax = Math.max(0, ...points.map((point) => Math.max(point.value, point.high)))

  // Die Skala rastet auf runde Schritte ein. Dadurch liegt die Null immer auf einer
  // Gitterlinie — genau die Grenze, um die es in einer Liquiditätskurve geht.
  const step = niceStep((rawMax - rawMin) / TARGET_TICKS)
  let yMin = Math.floor(rawMin / step) * step
  let yMax = Math.ceil(rawMax / step) * step
  if (yMax === yMin) {
    yMin -= step
    yMax += step
  }

  const x = (index: number) =>
    points.length <= 1
      ? PAD_LEFT + INNER_WIDTH / 2
      : PAD_LEFT + (index * INNER_WIDTH) / (points.length - 1)
  const y = (value: number) =>
    PAD_TOP + INNER_HEIGHT * (1 - (value - yMin) / (yMax - yMin))

  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(point.value)}`).join(' ')
  const zeroY = y(0)
  const area = `${line} L ${x(points.length - 1)} ${zeroY} L ${x(0)} ${zeroY} Z`

  // Das Band als geschlossene Fläche: obere Kante hin, untere Kante zurück.
  const hasBand = points.some((point) => point.high !== point.value || point.low !== point.value)
  const band = hasBand
    ? [
        ...points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(point.high)}`),
        ...points
          .map((point, index) => ({ point, index }))
          .reverse()
          .map(({ point, index }) => `L ${x(index)} ${y(point.low)}`),
        'Z',
      ].join(' ')
    : null

  const ticks: { value: number; y: number }[] = []
  for (let value = yMax; value >= yMin - step / 2; value -= step) {
    const snapped = Math.abs(value) < step / 1000 ? 0 : value
    ticks.push({ value: snapped, y: y(snapped) })
  }

  return { x, y, line, area, band, zeroY, ticks, yMin, yMax }
}
