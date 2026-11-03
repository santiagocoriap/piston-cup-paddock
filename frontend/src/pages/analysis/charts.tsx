import { useId, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/Icon'

const PALETTE = ['#e10600', '#38bdf8', '#facc15', '#4ade80', '#c084fc', '#fb923c', '#f472b6', '#2dd4bf', '#a3e635', '#94a3b8', '#818cf8', '#fda4af']

/** The same driver has the same color in every graph of a page: the color comes from the driver,
 * not from the place in a list. */
export function driverColor(driverId: number): string {
  return PALETTE[Math.abs(driverId) % PALETTE.length]
}

type Csv = () => (string | number | boolean | null | undefined)[][]

function download(name: string, content: string, type: string) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([content], { type }))
  link.download = name
  link.click()
  URL.revokeObjectURL(link.href)
}

/** One graph with its title, its explanation, and its tools: full screen, SVG, and CSV. With
 * "missing", the card says why the data is not enough, and it draws no graph. */
export function ChartCard({
  title,
  help,
  missing,
  csv,
  wide = false,
  children,
}: {
  title: string
  help?: string
  missing?: string | null
  csv?: Csv
  /** The graph takes the full width of the page, for example a table of laps. */
  wide?: boolean
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const box = useRef<HTMLElement>(null)
  const file = title.toLowerCase().replace(/[^a-z0-9]+/g, '-')

  function exportSvg() {
    const svg = box.current?.querySelector('svg.chart')
    if (svg) download(`${file}.svg`, new XMLSerializer().serializeToString(svg), 'image/svg+xml')
  }

  function exportCsv() {
    const text = csv!()
      .map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n')
    download(`${file}.csv`, text, 'text/csv')
  }

  return (
    <figure className={wide ? 'chart-card chart-wide' : 'chart-card'} ref={box}>
      <header className="chart-head">
        <h4>{title}</h4>
        {!missing && (
          <div className="chart-tools">
            <button type="button" className="chart-tool" onClick={() => box.current?.requestFullscreen?.()} aria-label={t('analysis.fullscreen', { title })}>
              <Icon name="expand" small />
            </button>
            <button type="button" className="chart-tool" onClick={exportSvg} aria-label={t('analysis.exportSvg', { title })}>
              SVG
            </button>
            {csv && (
              <button type="button" className="chart-tool" onClick={exportCsv} aria-label={t('analysis.exportCsv', { title })}>
                CSV
              </button>
            )}
          </div>
        )}
      </header>
      {missing ? <p className="muted chart-missing">{missing}</p> : children}
      {help && !missing && <figcaption className="muted">{help}</figcaption>}
    </figure>
  )
}

/** A group of graphs that the user can close. A closed group draws nothing. */
export function ChartGroup({ title, open: startOpen = false, children }: { title: string; open?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(startOpen)
  return (
    <details className="chart-group" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{title}</summary>
      {open && <div className="chart-grid">{children}</div>}
    </details>
  )
}

export type Driver = { id: number; name: string }

/** The drivers on the graphs. A click hides or shows a driver in all the graphs of the page. */
export function DriverFilter({ drivers, hidden, onChange }: { drivers: Driver[]; hidden: number[]; onChange: (next: number[]) => void }) {
  const { t } = useTranslation()
  return (
    <div className="chart-filter" role="group" aria-label={t('analysis.driversOnGraphs')}>
      {drivers.map((driver) => {
        const on = !hidden.includes(driver.id)
        return (
          <button
            key={driver.id}
            type="button"
            className={on ? 'chart-chip on' : 'chart-chip'}
            aria-pressed={on}
            onClick={() => onChange(on ? [...hidden, driver.id] : hidden.filter((id) => id !== driver.id))}
          >
            <span className="chart-swatch" style={{ background: on ? driverColor(driver.id) : 'transparent', borderColor: driverColor(driver.id) }} />
            {driver.name}
          </button>
        )
      })}
    </div>
  )
}

const WIDTH = 760
const niceStep = (span: number, count: number) => {
  const raw = span / Math.max(count, 1)
  const power = Math.pow(10, Math.floor(Math.log10(raw || 1)))
  const scaled = raw / power
  return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * power
}

export type LinePoint = { x: number; y: number | null; hollow?: boolean; mark?: boolean }
export type LineSeries = { key: number | string; label: string; color: string; points: LinePoint[]; dashed?: boolean }

/** Lines on one x axis. Move the mouse to read the values of a lap. Drag to zoom in, and a double
 * click shows all again. */
export function LineChart({
  series,
  xLabel,
  yLabel,
  formatY = (v) => String(Math.round(v * 100) / 100),
  invert = false,
  integerY = false,
  zero = false,
  step = false,
  height = 300,
  yLimit,
}: {
  series: LineSeries[]
  xLabel: string
  yLabel: string
  formatY?: (value: number) => string
  invert?: boolean
  integerY?: boolean
  zero?: boolean
  step?: boolean
  height?: number
  /** Values above this value stay on the top line of the graph. */
  yLimit?: number
}) {
  const { t } = useTranslation()
  const [hover, setHover] = useState<number | null>(null)
  const [zoom, setZoom] = useState<[number, number] | null>(null)
  const [drag, setDrag] = useState<[number, number] | null>(null)
  const pad = { left: 62, right: 14, top: 12, bottom: 34 }
  const clip = useId()
  const allX = [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b)
  if (allX.length === 0) return null
  const [minX, maxX] = zoom ?? [allX[0], allX[allX.length - 1]]
  const inView = allX.filter((x) => x >= minX && x <= maxX)
  const shown = (y: number) => (yLimit !== undefined ? Math.min(y, yLimit) : y)
  const ys = series.flatMap((s) => s.points.filter((p) => p.y !== null && p.x >= minX && p.x <= maxX).map((p) => shown(p.y as number)))
  let [minY, maxY] = [Math.min(...ys, zero ? 0 : Infinity), Math.max(...ys, zero ? 0 : -Infinity)]
  if (minY === maxY) [minY, maxY] = [minY - 1, maxY + 1]
  const px = (x: number) => pad.left + ((x - minX) / (maxX - minX || 1)) * (WIDTH - pad.left - pad.right)
  const py = (y: number) => {
    const share = (shown(y) - minY) / (maxY - minY)
    return pad.top + (invert ? share : 1 - share) * (height - pad.top - pad.bottom)
  }
  const stepY = integerY ? Math.max(1, Math.ceil((maxY - minY) / 8)) : niceStep(maxY - minY, 5)
  const ticksY: number[] = []
  for (let v = Math.ceil(minY / stepY) * stepY; v <= maxY; v += stepY) ticksY.push(v)
  const stepX = Math.max(1, Math.ceil(niceStep(maxX - minX, 10)))
  const ticksX = inView.filter((x) => Number.isInteger(x) && x % stepX === 0)

  function toX(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const value = minX + (((event.clientX - rect.left) * (WIDTH / rect.width) - pad.left) / (WIDTH - pad.left - pad.right)) * (maxX - minX)
    return inView.reduce((best, x) => (Math.abs(x - value) < Math.abs(best - value) ? x : best), inView[0])
  }

  const path = (s: LineSeries) => {
    let out = ''
    let before: LinePoint | null = null
    for (const p of s.points) {
      if (p.y === null || p.x < minX || p.x > maxX) {
        before = null
        continue
      }
      const [x, y] = [px(p.x).toFixed(1), py(p.y).toFixed(1)]
      if (before && step) out += `H${x}V${y}`
      else out += `${before ? 'L' : 'M'}${x},${y}`
      before = p
    }
    return out
  }

  return (
    <div className="chart-plot">
      <svg
        className="chart"
        viewBox={`0 0 ${WIDTH} ${height}`}
        role="img"
        aria-label={yLabel}
        onMouseMove={(event) => {
          const x = toX(event)
          setHover(x)
          if (drag) setDrag([drag[0], x])
        }}
        onMouseLeave={() => {
          setHover(null)
          setDrag(null)
        }}
        onMouseDown={(event) => {
          const x = toX(event)
          setDrag([x, x])
        }}
        onMouseUp={() => {
          if (drag && drag[0] !== drag[1]) setZoom([Math.min(...drag), Math.max(...drag)])
          setDrag(null)
        }}
        onDoubleClick={() => setZoom(null)}
      >
        <clipPath id={clip}>
          <rect x={pad.left - 6} y={0} width={WIDTH - pad.left - pad.right + 12} height={height - pad.bottom + 6} />
        </clipPath>
        {ticksY.map((v) => (
          <g key={v}>
            <line x1={pad.left} x2={WIDTH - pad.right} y1={py(v)} y2={py(v)} className="chart-grid-line" />
            <text x={pad.left - 8} y={py(v) + 4} textAnchor="end" className="chart-axis">
              {formatY(v)}
            </text>
          </g>
        ))}
        {zero && minY < 0 && <line x1={pad.left} x2={WIDTH - pad.right} y1={py(0)} y2={py(0)} className="chart-zero" />}
        {ticksX.map((x) => (
          <text key={x} x={px(x)} y={height - 16} textAnchor="middle" className="chart-axis">
            {x}
          </text>
        ))}
        <text x={(WIDTH + pad.left) / 2} y={height - 2} textAnchor="middle" className="chart-axis">
          {xLabel}
        </text>
        <g clipPath={`url(#${clip})`}>
          {series.map((s) => (
            <path key={s.key} d={path(s)} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '5 4' : undefined} />
          ))}
          {series.map((s) =>
            s.points
              .filter((p) => p.y !== null && p.x >= minX && p.x <= maxX && (p.hollow || p.mark || inView.length <= 40))
              .map((p) => (
                <circle
                  key={`${s.key}-${p.x}`}
                  cx={px(p.x)}
                  cy={py(p.y as number)}
                  r={p.mark ? 4.5 : 3}
                  fill={p.hollow ? 'var(--surface-1)' : s.color}
                  stroke={s.color}
                  strokeWidth={p.hollow ? 1.5 : 0}
                />
              )),
          )}
        </g>
        {hover !== null && <line x1={px(hover)} x2={px(hover)} y1={pad.top} y2={height - pad.bottom} className="chart-cursor" />}
        {drag && drag[0] !== drag[1] && (
          <rect x={px(Math.min(...drag))} y={pad.top} width={Math.abs(px(drag[1]) - px(drag[0]))} height={height - pad.top - pad.bottom} className="chart-drag" />
        )}
      </svg>
      {hover !== null && (
        <div className="chart-tip" style={{ left: `${(px(hover) / WIDTH) * 100}%` }}>
          <strong>
            {xLabel} {hover}
          </strong>
          {series
            .map((s) => ({ s, y: s.points.find((p) => p.x === hover)?.y ?? null }))
            .filter((row) => row.y !== null)
            .sort((a, b) => (invert ? (a.y as number) - (b.y as number) : (b.y as number) - (a.y as number)))
            .map(({ s, y }) => (
              <span key={s.key}>
                <span className="chart-swatch" style={{ background: s.color, borderColor: s.color }} />
                {s.label}: {formatY(y as number)}
              </span>
            ))}
        </div>
      )}
      {zoom && (
        <button type="button" className="chart-reset" onClick={() => setZoom(null)}>
          {t('analysis.resetZoom')}
        </button>
      )}
    </div>
  )
}

export type BarRow = { key: number | string; label: string; value: number | null; color?: string; note?: string; muted?: boolean }

/** Horizontal bars. Negative values go to the left of the zero line. */
export function BarChart({ rows, format = (v) => String(v), label }: { rows: BarRow[]; format?: (value: number) => string; label: string }) {
  const known = rows.filter((r) => r.value !== null)
  const left = Math.max(0, ...known.map((r) => -(r.value as number)))
  const right = Math.max(0, ...known.map((r) => r.value as number))
  const total = left + right || 1
  const height = 28
  const text = (row: BarRow) => `${row.value === null ? '—' : format(row.value)}${row.note ? ` · ${row.note}` : ''}`
  const pad = { left: 150, right: Math.min(320, 16 + 6.6 * Math.max(0, ...rows.map((row) => text(row).length))) }
  const span = WIDTH - pad.left - pad.right
  const zero = pad.left + (left / total) * span
  return (
    <svg className="chart" viewBox={`0 0 ${WIDTH} ${rows.length * height + 8}`} role="img" aria-label={label}>
      {rows.map((row, index) => {
        const y = index * height + 4
        const width = row.value === null ? 0 : (Math.abs(row.value) / total) * span
        const x = row.value !== null && row.value < 0 ? zero - width : zero
        return (
          <g key={row.key} opacity={row.muted ? 0.45 : 1}>
            <text x={pad.left - 8} y={y + 16} textAnchor="end" className="chart-label">
              {row.label}
            </text>
            <rect x={x} y={y + 3} width={Math.max(width, row.value === null ? 0 : 1.5)} height={height - 8} rx={3} fill={row.color ?? 'var(--brand)'}>
              <title>{`${row.label}: ${row.value === null ? '—' : format(row.value)}`}</title>
            </rect>
            <text x={x + (row.value !== null && row.value < 0 ? -6 : width + 6)} y={y + 16} textAnchor={row.value !== null && row.value < 0 ? 'end' : 'start'} className="chart-value">
              {text(row)}
            </text>
          </g>
        )
      })}
      <line x1={zero} x2={zero} y1={0} y2={rows.length * height + 8} className="chart-zero" />
    </svg>
  )
}

export type StackRow = { key: number | string; label: string; parts: { key: string; label?: string; value: number; color: string }[]; note?: string }

/** Bars of parts that add up. "share": each bar fills the width, so the bars show percents. */
export function StackChart({ rows, label, share = false, legend, format = (v) => String(v) }: { rows: StackRow[]; label: string; share?: boolean; legend?: { label: string; color: string }[]; format?: (value: number) => string }) {
  const height = 28
  const pad = { left: 150, right: Math.min(240, 40 + 6.6 * Math.max(0, ...rows.map((row) => (row.note ?? '').length))) }
  const span = WIDTH - pad.left - pad.right
  const top = Math.max(1, ...rows.map((r) => r.parts.reduce((sum, p) => sum + p.value, 0)))
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${WIDTH} ${rows.length * height + 8}`} role="img" aria-label={label}>
        {rows.map((row, index) => {
          const y = index * height + 4
          const total = row.parts.reduce((sum, p) => sum + p.value, 0)
          const scale = span / (share ? total || 1 : top)
          let x = pad.left
          return (
            <g key={row.key}>
              <text x={pad.left - 8} y={y + 16} textAnchor="end" className="chart-label">
                {row.label}
              </text>
              {row.parts.map((part, partIndex) => {
                const width = part.value * scale
                const rect = (
                  <rect key={`${part.key}-${partIndex}`} x={x} y={y + 3} width={Math.max(width - 1, 0)} height={height - 8} rx={2} fill={part.color}>
                    <title>{`${row.label} · ${part.label ?? part.key}: ${format(part.value)}`}</title>
                  </rect>
                )
                x += width
                return rect
              })}
              <text x={x + 6} y={y + 16} className="chart-value">
                {row.note ?? format(total)}
              </text>
            </g>
          )
        })}
      </svg>
      {legend && (
        <div className="chart-legend">
          {legend.map((item) => (
            <span key={item.label}>
              <span className="chart-swatch" style={{ background: item.color, borderColor: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      )}
    </>
  )
}

export type BoxRow = { key: number | string; label: string; color: string; q1: number; q3: number; median: number; low: number; high: number; outliers: number[]; note?: string }

/** Box plots: the box holds the middle half of the values, and the line in it is the median. */
export function BoxChart({ rows, format, label }: { rows: BoxRow[]; format: (value: number) => string; label: string }) {
  const height = 34
  const pad = { left: 150, right: Math.min(240, 16 + 6.6 * Math.max(0, ...rows.map((row) => (row.note ?? format(row.median)).length))), top: 4, bottom: 26 }
  const low = Math.min(...rows.flatMap((r) => [r.low, ...r.outliers]))
  const high = Math.max(...rows.flatMap((r) => [r.high, ...r.outliers]))
  const px = (v: number) => pad.left + ((v - low) / (high - low || 1)) * (WIDTH - pad.left - pad.right)
  const total = rows.length * height + pad.top + pad.bottom
  const ticks: number[] = []
  const step = niceStep(high - low, 5)
  for (let v = Math.ceil(low / step) * step; v <= high; v += step) ticks.push(v)
  return (
    <svg className="chart" viewBox={`0 0 ${WIDTH} ${total}`} role="img" aria-label={label}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={px(v)} x2={px(v)} y1={pad.top} y2={total - pad.bottom} className="chart-grid-line" />
          <text x={px(v)} y={total - 8} textAnchor="middle" className="chart-axis">
            {format(v)}
          </text>
        </g>
      ))}
      {rows.map((row, index) => {
        const y = pad.top + index * height + height / 2
        return (
          <g key={row.key}>
            <text x={pad.left - 8} y={y + 4} textAnchor="end" className="chart-label">
              {row.label}
            </text>
            <line x1={px(row.low)} x2={px(row.high)} y1={y} y2={y} stroke={row.color} />
            <rect x={px(row.q1)} y={y - 10} width={Math.max(px(row.q3) - px(row.q1), 1)} height={20} fill={row.color} fillOpacity={0.3} stroke={row.color}>
              <title>{`${row.label}: ${format(row.median)}`}</title>
            </rect>
            <line x1={px(row.median)} x2={px(row.median)} y1={y - 10} y2={y + 10} stroke={row.color} strokeWidth={3} />
            {row.outliers.map((v, i) => (
              <circle key={i} cx={px(v)} cy={y} r={3} fill="none" stroke={row.color} />
            ))}
            <text x={WIDTH - pad.right + 8} y={y + 4} className="chart-value">
              {row.note ?? format(row.median)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export type HeatCell = { value: number | null; text?: string; mark?: string; title?: string }

/** A table of colors. Low values are green and high values are red, unless "reverse" is set. */
export function HeatMap({ rows, columns, label, reverse = false, low, high }: { rows: { key: number | string; label: string; cells: HeatCell[] }[]; columns: string[]; label: string; reverse?: boolean; low?: number; high?: number }) {
  const cell = Math.max(22, Math.min(46, (WIDTH - 150) / Math.max(columns.length, 1)))
  const rowHeight = 26
  const values = rows.flatMap((r) => r.cells.map((c) => c.value)).filter((v): v is number => v !== null)
  const [min, max] = [low ?? Math.min(...values), high ?? Math.max(...values)]
  const color = (v: number) => {
    const share = Math.max(0, Math.min(1, (v - min) / (max - min || 1)))
    const hue = (reverse ? share : 1 - share) * 130
    return `hsl(${hue} 70% 36%)`
  }
  const width = 150 + cell * columns.length
  return (
    <div className="chart-scroll">
      <svg className="chart" viewBox={`0 0 ${Math.max(width, 300)} ${rows.length * rowHeight + 24}`} style={{ minWidth: Math.min(width, 760) }} role="img" aria-label={label}>
        {columns.map((name, index) => (
          <text key={index} x={150 + index * cell + cell / 2} y={14} textAnchor="middle" className="chart-axis">
            {name}
          </text>
        ))}
        {rows.map((row, r) => (
          <g key={row.key}>
            <text x={142} y={24 + r * rowHeight + 17} textAnchor="end" className="chart-label">
              {row.label}
            </text>
            {row.cells.map((c, index) => (
              <g key={index}>
                <rect x={150 + index * cell} y={24 + r * rowHeight} width={cell - 2} height={rowHeight - 2} rx={2} fill={c.value === null ? 'var(--surface-3)' : color(c.value)}>
                  <title>{c.title ?? ''}</title>
                </rect>
                {(c.mark ?? c.text) && (
                  <text x={150 + index * cell + cell / 2 - 1} y={24 + r * rowHeight + 16} textAnchor="middle" className="chart-cell">
                    {c.mark ?? c.text}
                  </text>
                )}
              </g>
            ))}
          </g>
        ))}
      </svg>
    </div>
  )
}

export type ScatterPoint = { key: number | string; label: string; x: number; y: number; color: string; strong?: boolean }

/** Points with a name. A line goes through the middle value of each axis. */
export function ScatterChart({ points, xLabel, yLabel, formatX = String, formatY = String, invertY = false, diagonal = false }: { points: ScatterPoint[]; xLabel: string; yLabel: string; formatX?: (v: number) => string; formatY?: (v: number) => string; invertY?: boolean; diagonal?: boolean }) {
  const height = 340
  const pad = { left: 62, right: 24, top: 14, bottom: 40 }
  const range = (values: number[]) => {
    const [a, b] = [Math.min(...values), Math.max(...values)]
    const margin = (b - a || 1) * 0.1
    return [a - margin, b + margin]
  }
  const [minX, maxX] = range(points.map((p) => p.x))
  const [minY, maxY] = range(points.map((p) => p.y))
  const px = (v: number) => pad.left + ((v - minX) / (maxX - minX)) * (WIDTH - pad.left - pad.right)
  const py = (v: number) => {
    const share = (v - minY) / (maxY - minY)
    return pad.top + (invertY ? share : 1 - share) * (height - pad.top - pad.bottom)
  }
  const ticks = (a: number, b: number) => {
    const step = niceStep(b - a, 5)
    const out: number[] = []
    for (let v = Math.ceil(a / step) * step; v <= b; v += step) out.push(v)
    return out
  }
  return (
    <svg className="chart" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={`${xLabel} / ${yLabel}`}>
      {ticks(minY, maxY).map((v) => (
        <g key={v}>
          <line x1={pad.left} x2={WIDTH - pad.right} y1={py(v)} y2={py(v)} className="chart-grid-line" />
          <text x={pad.left - 8} y={py(v) + 4} textAnchor="end" className="chart-axis">
            {formatY(v)}
          </text>
        </g>
      ))}
      {ticks(minX, maxX).map((v) => (
        <text key={v} x={px(v)} y={height - 22} textAnchor="middle" className="chart-axis">
          {formatX(v)}
        </text>
      ))}
      <text x={(WIDTH + pad.left) / 2} y={height - 4} textAnchor="middle" className="chart-axis">
        {xLabel}
      </text>
      <text x={14} y={height / 2} transform={`rotate(-90 14 ${height / 2})`} textAnchor="middle" className="chart-axis">
        {yLabel}
      </text>
      {diagonal && <line x1={px(Math.max(minX, minY))} y1={py(Math.max(minX, minY))} x2={px(Math.min(maxX, maxY))} y2={py(Math.min(maxX, maxY))} className="chart-zero" />}
      {points.map((p) => (
        <g key={p.key}>
          <circle cx={px(p.x)} cy={py(p.y)} r={p.strong ? 8 : 5.5} fill={p.color} stroke={p.strong ? 'var(--ink)' : 'none'} strokeWidth={2}>
            <title>{`${p.label}: ${formatX(p.x)} · ${formatY(p.y)}`}</title>
          </circle>
          <text x={px(p.x) + 9} y={py(p.y) + 4} className="chart-value">
            {p.label}
          </text>
        </g>
      ))}
    </svg>
  )
}

/** A radar graph of scores from 0 to 100. */
export function RadarChart({ axes, series, label }: { axes: string[]; series: { key: number | string; label: string; color: string; values: (number | null)[]; dashed?: boolean }[]; label: string }) {
  const size = 360
  const middle = size / 2
  const radius = 122
  const at = (index: number, value: number): [number, number] => {
    const angle = (Math.PI * 2 * index) / axes.length - Math.PI / 2
    return [middle + (Math.cos(angle) * radius * value) / 100, middle + (Math.sin(angle) * radius * value) / 100]
  }
  return (
    <>
      <svg className="chart chart-radar" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
        {[25, 50, 75, 100].map((ring) => (
          <polygon key={ring} points={axes.map((_, i) => at(i, ring).join(',')).join(' ')} fill="none" className="chart-grid-line" />
        ))}
        {axes.map((name, index) => {
          const [x, y] = at(index, 100)
          const [tx, ty] = at(index, 116)
          return (
            <g key={name}>
              <line x1={middle} y1={middle} x2={x} y2={y} className="chart-grid-line" />
              <text x={tx} y={ty + 4} textAnchor="middle" className="chart-axis">
                {name}
              </text>
            </g>
          )
        })}
        {series.map((s) => (
          <polygon
            key={s.key}
            points={s.values.map((v, i) => at(i, v ?? 0).join(',')).join(' ')}
            fill={s.color}
            fillOpacity={0.2}
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? '5 4' : undefined}
          >
            <title>{`${s.label}: ${s.values.map((v, i) => `${axes[i]} ${v ?? '—'}`).join(' · ')}`}</title>
          </polygon>
        ))}
      </svg>
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.key}>
            <span className="chart-swatch" style={{ background: s.color, borderColor: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </>
  )
}

/** The graphs that the current data cannot give, and what each one needs. */
export function NeedsData({ items }: { items: string[] }) {
  const { t } = useTranslation()
  return (
    <details className="chart-needs">
      <summary>{t('analysis.needsData', { count: items.length })}</summary>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  )
}
