import { useMemo, useState } from 'react'
import type { LiquidityResponse } from '@/api/journal'
import {
  HEIGHT,
  INNER_WIDTH,
  PAD_BOTTOM,
  PAD_LEFT,
  PAD_RIGHT,
  PAD_TOP,
  WIDTH,
  buildChartGeometry,
  formatAxis,
  formatMoney,
  formatPeriod,
  parseAmount,
} from './liquidity-chart-geometry'
import type { ChartPoint } from './liquidity-chart-geometry'

const POSITIVE = '#2563eb'
const NEGATIVE = '#dc2626'

export function LiquidityChart({ data }: { data: LiquidityResponse }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)

  const points = useMemo<ChartPoint[]>(
    () => [
      {
        label: 'jetzt',
        value: parseAmount(data.start_balance),
        low: parseAmount(data.start_balance),
        high: parseAmount(data.start_balance),
        detail: null,
      },
      ...data.months.map((month) => ({
        label: formatPeriod(month.period),
        value: parseAmount(month.closing_balance),
        low: parseAmount(month.closing_low),
        high: parseAmount(month.closing_high),
        detail: month,
      })),
    ],
    [data],
  )

  const geometry = useMemo(() => buildChartGeometry(points), [points])
  const lowest = parseAmount(data.lowest_balance)
  const lowestLow = parseAmount(data.lowest_balance_low)
  const uncovered = parseAmount(data.uncovered_average_per_month)
  const goesNegative = lowest < 0
  const hasBand = geometry.band !== null

  if (data.months.length === 0) {
    return (
      <p className="text-sm text-gray-400">
        Noch keine Prognose möglich — dafür braucht es Buchungshistorie je Leistung.
      </p>
    )
  }

  const hovered = hoverIndex !== null ? points[hoverIndex] : null

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400">Tiefstand</p>
          <p
            className={`text-2xl font-semibold tabular-nums ${goesNegative ? 'text-red-600' : 'text-gray-900'}`}
          >
            {formatMoney(lowest, data.currency)}
          </p>
        </div>
        {hasBand ? (
          <div>
            <p className="text-xs uppercase tracking-wide text-gray-400">Ungünstiger Verlauf</p>
            <p
              className={`text-2xl font-semibold tabular-nums ${lowestLow < 0 ? 'text-red-600' : 'text-gray-900'}`}
            >
              {formatMoney(lowestLow, data.currency)}
            </p>
          </div>
        ) : null}
        <p className="text-sm text-gray-500">
          {goesNegative ? (
            <span className="font-medium text-red-600">
              ⚠ Deckung reicht nicht bis zum Ende des Horizonts
            </span>
          ) : (
            'Der Saldo bleibt über den gesamten Horizont positiv.'
          )}
          {data.lowest_period ? ` (${formatPeriod(data.lowest_period)})` : ''}
        </p>
      </div>

      <div className="relative">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full"
          role="img"
          aria-label={`Liquiditätsvorschau bis ${formatPeriod(data.months[data.months.length - 1].period)}, Tiefstand ${formatMoney(lowest, data.currency)}`}
          onMouseLeave={() => setHoverIndex(null)}
          onMouseMove={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect()
            if (bounds.width === 0) return
            const svgX = ((event.clientX - bounds.left) / bounds.width) * WIDTH
            const ratio = (svgX - PAD_LEFT) / INNER_WIDTH
            const index = Math.round(ratio * (points.length - 1))
            setHoverIndex(Math.min(Math.max(index, 0), points.length - 1))
          }}
        >
          <defs>
            <clipPath id="liquidity-above">
              <rect x="0" y="0" width={WIDTH} height={Math.max(geometry.zeroY, 0)} />
            </clipPath>
            <clipPath id="liquidity-below">
              <rect
                x="0"
                y={Math.max(geometry.zeroY, 0)}
                width={WIDTH}
                height={Math.max(HEIGHT - geometry.zeroY, 0)}
              />
            </clipPath>
          </defs>

          {geometry.ticks.map((tick) => (
            <g key={tick.value}>
              <line
                x1={PAD_LEFT}
                x2={WIDTH - PAD_RIGHT}
                y1={tick.y}
                y2={tick.y}
                stroke="#e5e7eb"
                strokeWidth="1"
              />
              <text
                x={PAD_LEFT - 8}
                y={tick.y + 3}
                textAnchor="end"
                className="fill-gray-400"
                fontSize="10"
              >
                {formatAxis(tick.value)}
              </text>
            </g>
          ))}

          {/* Nulllinie: die eigentliche Entscheidungsgrenze */}
          <line
            x1={PAD_LEFT}
            x2={WIDTH - PAD_RIGHT}
            y1={geometry.zeroY}
            y2={geometry.zeroY}
            stroke="#9ca3af"
            strokeWidth="1.5"
          />

          {geometry.band ? <path d={geometry.band} fill="#94a3b8" opacity="0.22" /> : null}

          <path d={geometry.area} fill={POSITIVE} opacity="0.12" clipPath="url(#liquidity-above)" />
          <path d={geometry.area} fill={NEGATIVE} opacity="0.12" clipPath="url(#liquidity-below)" />
          <path
            d={geometry.line}
            fill="none"
            stroke={POSITIVE}
            strokeWidth="2"
            clipPath="url(#liquidity-above)"
          />
          <path
            d={geometry.line}
            fill="none"
            stroke={NEGATIVE}
            strokeWidth="2"
            clipPath="url(#liquidity-below)"
          />

          {points.map((point, index) =>
            index === 0 || index === points.length - 1 || index % 2 === 0 ? (
              <text
                key={point.label}
                x={geometry.x(index)}
                y={HEIGHT - 10}
                textAnchor="middle"
                className="fill-gray-400"
                fontSize="10"
              >
                {point.label}
              </text>
            ) : null,
          )}

          {hoverIndex !== null && hovered ? (
            <g>
              <line
                x1={geometry.x(hoverIndex)}
                x2={geometry.x(hoverIndex)}
                y1={PAD_TOP}
                y2={HEIGHT - PAD_BOTTOM}
                stroke="#9ca3af"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <circle
                cx={geometry.x(hoverIndex)}
                cy={geometry.y(hovered.value)}
                r="4.5"
                fill={hovered.value < 0 ? NEGATIVE : POSITIVE}
                stroke="#ffffff"
                strokeWidth="2"
              />
            </g>
          ) : null}
        </svg>

        {hovered ? (
          <div
            className="pointer-events-none absolute top-2 z-10 w-64 rounded-lg border border-gray-200 bg-white p-2 text-xs shadow-lg"
            style={geometry.x(hoverIndex ?? 0) / WIDTH > 0.6 ? { left: '2%' } : { right: '2%' }}
          >
            <p className="mb-1 font-semibold text-gray-900">
              {hovered.detail ? formatPeriod(hovered.detail.period) : 'Aktueller Stand'}
            </p>
            {hovered.detail ? (
              <dl className="space-y-0.5 text-gray-600">
                <div className="flex justify-between gap-3">
                  <dt>Einzahlungen</dt>
                  <dd className="tabular-nums">
                    {formatMoney(parseAmount(hovered.detail.inflow), data.currency)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Auszahlungen</dt>
                  <dd className="tabular-nums">
                    {formatMoney(parseAmount(hovered.detail.outflow), data.currency)}
                  </dd>
                </div>
              </dl>
            ) : null}
            <p className="mt-1 flex justify-between gap-3 border-t border-gray-100 pt-1 font-medium text-gray-900">
              <span>Saldo</span>
              <span className={`tabular-nums ${hovered.value < 0 ? 'text-red-600' : ''}`}>
                {formatMoney(hovered.value, data.currency)}
              </span>
            </p>
            {hovered.detail && hovered.high !== hovered.low ? (
              <p className="mt-0.5 flex justify-between gap-3 text-gray-500">
                <span>Bandbreite</span>
                <span className="tabular-nums">
                  {formatMoney(hovered.low, data.currency)} …{' '}
                  {formatMoney(hovered.high, data.currency)}
                </span>
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
        <p>
          Prognose ab {formatPeriod(data.months[0].period)}
          {data.as_of ? `, Stand der Buchungen ${data.as_of.split('-').reverse().join('.')}` : ''}.
          {Math.abs(uncovered) >= 1
            ? ` Nicht enthalten: rund ${formatMoney(uncovered, data.currency)} pro Monat aus Buchungen ohne prognostizierbare Leistung.`
            : ''}
          {hasBand
            ? ' Das graue Band ist die Unsicherheit aus den am Rückvergleich gemessenen Fehlern der einzelnen Regeln.'
            : ''}
        </p>
        <button
          type="button"
          onClick={() => setShowTable((current) => !current)}
          className="shrink-0 rounded border border-gray-300 px-2 py-1 hover:bg-gray-50"
        >
          {showTable ? 'Zahlen ausblenden' : 'Zahlen anzeigen'}
        </button>
      </div>

      {showTable ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Monat</th>
                <th className="px-3 py-1.5 text-right font-medium">Anfang</th>
                <th className="px-3 py-1.5 text-right font-medium">Ein</th>
                <th className="px-3 py-1.5 text-right font-medium">Aus</th>
                <th className="px-3 py-1.5 text-right font-medium">Ende</th>
                {hasBand ? (
                  <th className="px-3 py-1.5 text-right font-medium">Bandbreite</th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.months.map((month) => (
                <tr key={month.period}>
                  <td className="px-3 py-1.5">{formatPeriod(month.period)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-gray-500">
                    {formatMoney(parseAmount(month.opening_balance), data.currency)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-gray-500">
                    {formatMoney(parseAmount(month.inflow), data.currency)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-gray-500">
                    {formatMoney(parseAmount(month.outflow), data.currency)}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-medium tabular-nums ${
                      parseAmount(month.closing_balance) < 0 ? 'text-red-600' : 'text-gray-900'
                    }`}
                  >
                    {formatMoney(parseAmount(month.closing_balance), data.currency)}
                  </td>
                  {hasBand ? (
                    <td className="px-3 py-1.5 text-right tabular-nums text-gray-500">
                      {formatMoney(parseAmount(month.closing_low), data.currency)} …{' '}
                      {formatMoney(parseAmount(month.closing_high), data.currency)}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
