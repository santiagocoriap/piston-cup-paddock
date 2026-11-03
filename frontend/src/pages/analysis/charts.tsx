import { useId, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
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

/** A copy of a graph that keeps its look in another program: the page style does not go with it. */
function standalone(svg: SVGSVGElement): string {
  const copy = svg.cloneNode(true) as SVGSVGElement
  const from = svg.querySelectorAll('*')
  copy.querySelectorAll('*').forEach((element, index) => {
    const style = getComputedStyle(from[index])
    for (const name of ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'font-size', 'font-family', 'font-weight']) {
      element.setAttribute(name, style.getPropertyValue(name))
    }
  })
  return new XMLSerializer().serializeToString(copy)
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
    const svg = box.current?.querySelector<SVGSVGElement>('svg.chart')
    if (svg) download(`${file}.svg`, standalone(svg), 'image/svg+xml')
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

/** The size of the graphs before the page measures them, and in tests. */
const WIDTH = 760
/** The width of a text in pixels. The graphs use one font size, so an estimate is enough. */
const textWidth = (text: string, size = 12) => text.length * size * 0.56
const LABEL = 13

/** A box that fills its card. A graph draws in real pixels, so the text keeps its size at any
 * width, and a graph fills the height of a taller graph on the same row. */
function PlotBox({ min, children }: { min: number; children: (width: number, height: number) => ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: WIDTH, height: min })
  useLayoutEffect(() => {
    const element = box.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (width > 0) setSize({ width, height: Math.max(height, min) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [min])
  return (
    <div className="chart-box" ref={box} style={{ minHeight: min }}>
      {children(size.width, Math.max(size.height, min))}
    </div>
  )
}

/** The room for the row names: the longest name, up to 30 % of the graph. */
function labelColumn(labels: string[], width: number) {
  const room = Math.max(60, Math.min(width * 0.3, Math.max(0, ...labels.map((l) => textWidth(l, LABEL))) + 12))
  const fit = (label: string) => {
    const chars = Math.floor((room - 10) / (LABEL * 0.56))
    return label.length > chars ? `${label.slice(0, Math.max(chars - 1, 1))}…` : label
  }
  return { room, fit }
}

/** The height of each row: rows fill the box, up to a height that still looks like a bar. */
function rowLayout(count: number, height: number, top = 0, bottom = 0, biggest = 46) {
  const row = Math.min(biggest, (height - top - bottom) / Math.max(count, 1))
  const start = top + (height - top - bottom - row * count) / 2
  return { row, start, bar: Math.min(row - 8, 26) }
}

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
  formatX = (v) => String(v),
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
  formatX?: (value: number) => string
  invert?: boolean
  integerY?: boolean
  zero?: boolean
  step?: boolean
  height?: number
  /** Values above this value stay on the top line of the graph. */
  yLimit?: number
}) {
  if (!series.some((s) => s.points.length > 0)) return null
  return (
    <PlotBox min={height}>
      {(width, boxHeight) => (
        <LinePlot {...{ series, xLabel, yLabel, formatY, formatX, invert, integerY, zero, step, yLimit, width, height: boxHeight }} />
      )}
    </PlotBox>
  )
}

function LinePlot({
  series,
  xLabel,
  yLabel,
  formatY,
  formatX,
  invert,
  integerY,
  zero,
  step,
  yLimit,
  width,
  height,
}: {
  series: LineSeries[]
  xLabel: string
  yLabel: string
  formatY: (value: number) => string
  formatX: (value: number) => string
  invert: boolean
  integerY: boolean
  zero: boolean
  step: boolean
  yLimit?: number
  width: number
  height: number
}) {
  const { t } = useTranslation()
  const [hover, setHover] = useState<number | null>(null)
  const [zoom, setZoom] = useState<[number, number] | null>(null)
  const [drag, setDrag] = useState<[number, number] | null>(null)
  const clip = useId()
  const allX = [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b)
  const [minX, maxX] = zoom ?? [allX[0], allX[allX.length - 1]]
  const inView = allX.filter((x) => x >= minX && x <= maxX)
  const shown = (y: number) => (yLimit !== undefined ? Math.min(y, yLimit) : y)
  const ys = series.flatMap((s) => s.points.filter((p) => p.y !== null && p.x >= minX && p.x <= maxX).map((p) => shown(p.y as number)))
  let [minY, maxY] = [Math.min(...ys, zero ? 0 : Infinity), Math.max(...ys, zero ? 0 : -Infinity)]
  if (!Number.isFinite(minY)) [minY, maxY] = [0, 1]
  if (minY === maxY) [minY, maxY] = [minY - 1, maxY + 1]
  const stepY = integerY ? Math.max(1, Math.ceil((maxY - minY) / 8)) : niceStep(maxY - minY, Math.max(3, height / 60))
  const ticksY: number[] = []
  for (let v = Math.ceil(minY / stepY) * stepY; v <= maxY; v += stepY) ticksY.push(v)
  const pad = { left: 14 + Math.max(24, ...ticksY.map((v) => textWidth(formatY(v)))), right: 14, top: 12, bottom: 40 }
  const px = (x: number) => pad.left + ((x - minX) / (maxX - minX || 1)) * (width - pad.left - pad.right)
  const py = (y: number) => {
    const share = (shown(y) - minY) / (maxY - minY)
    return pad.top + (invert ? share : 1 - share) * (height - pad.top - pad.bottom)
  }
  const stepX = niceStep(maxX - minX || 1, Math.max(2, width / 70))
  const ticksX: number[] = []
  for (let v = Math.ceil(minX / stepX) * stepX; v <= maxX; v += stepX) ticksX.push(v)

  function toX(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const value = minX + ((event.clientX - rect.left - pad.left) / (width - pad.left - pad.right)) * (maxX - minX)
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
    <>
      <svg
        className="chart"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
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
          <rect x={pad.left - 6} y={0} width={width - pad.left - pad.right + 12} height={height - pad.bottom + 6} />
        </clipPath>
        {ticksY.map((v) => (
          <g key={v}>
            <line x1={pad.left} x2={width - pad.right} y1={py(v)} y2={py(v)} className="chart-grid-line" />
            <text x={pad.left - 8} y={py(v) + 4} textAnchor="end" className="chart-axis">
              {formatY(v)}
            </text>
          </g>
        ))}
        {zero && minY < 0 && <line x1={pad.left} x2={width - pad.right} y1={py(0)} y2={py(0)} className="chart-zero" />}
        {ticksX.map((x) => (
          <text key={x} x={px(x)} y={height - 22} textAnchor="middle" className="chart-axis">
            {formatX(x)}
          </text>
        ))}
        <text x={(width + pad.left - pad.right) / 2} y={height - 4} textAnchor="middle" className="chart-axis">
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
        <div className="chart-tip" style={px(hover) > width / 2 ? { right: width - px(hover) + 12 } : { left: px(hover) + 12 }}>
          <strong>
            {xLabel} {formatX(hover)}
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
    </>
  )
}

export type BarRow = { key: number | string; label: string; value: number | null; color?: string; note?: string; muted?: boolean }

/** Horizontal bars. Negative values go to the left of the zero line. The text of a bar has its
 * own room on each side, so it never covers a name or goes out of the box. */
export function BarChart({ rows, format = (v) => String(v), label }: { rows: BarRow[]; format?: (value: number) => string; label: string }) {
  return (
    <PlotBox min={rows.length * 30 + 8}>
      {(width, height) => {
        const names = labelColumn(rows.map((r) => r.label), width)
        const known = rows.filter((r) => r.value !== null)
        const left = Math.max(0, ...known.map((r) => -(r.value as number)))
        const right = Math.max(0, ...known.map((r) => r.value as number))
        const total = left + right || 1
        const short = (row: BarRow) => (row.value === null ? '—' : format(row.value))
        const roomFor = (text: (row: BarRow) => string) => ({
          before: Math.max(0, ...rows.filter((r) => r.value !== null && r.value < 0).map((r) => textWidth(text(r)) + 10)),
          after: Math.max(0, ...rows.filter((r) => r.value === null || r.value >= 0).map((r) => textWidth(text(r)) + 10)),
        })
        const full = (row: BarRow) => `${short(row)}${row.note ? ` · ${row.note}` : ''}`
        // On a narrow screen the notes go away, and the bars keep their room.
        const long = roomFor(full)
        const useFull = width - names.room - long.before - long.after >= width * 0.25
        const text = useFull ? full : short
        const { before, after } = useFull ? long : roomFor(short)
        const span = Math.max(30, width - names.room - before - after)
        const zero = names.room + before + (left / total) * span
        const { row, start, bar } = rowLayout(rows.length, height)
        return (
          <svg className="chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
            {rows.map((item, index) => {
              const y = start + index * row + row / 2
              const size = item.value === null ? 0 : (Math.abs(item.value) / total) * span
              const negative = item.value !== null && item.value < 0
              return (
                <g key={item.key} opacity={item.muted ? 0.45 : 1}>
                  <text x={names.room - 8} y={y + 4} textAnchor="end" className="chart-label">
                    <title>{item.label}</title>
                    {names.fit(item.label)}
                  </text>
                  <rect x={negative ? zero - size : zero} y={y - bar / 2} width={Math.max(size, item.value === null ? 0 : 1.5)} height={bar} rx={3} fill={item.color ?? 'var(--brand)'}>
                    <title>{`${item.label}: ${full(item)}`}</title>
                  </rect>
                  <text x={negative ? zero - size - 6 : zero + size + 6} y={y + 4} textAnchor={negative ? 'end' : 'start'} className="chart-value">
                    {text(item)}
                  </text>
                </g>
              )
            })}
            <line x1={zero} x2={zero} y1={start} y2={start + row * rows.length} className="chart-zero" />
          </svg>
        )
      }}
    </PlotBox>
  )
}

export type StackRow = { key: number | string; label: string; parts: { key: string; label?: string; value: number; color: string }[]; note?: string }

/** Bars of parts that add up. "share": each bar fills the width, so the bars show percents. */
export function StackChart({ rows, label, share = false, legend, format = (v) => String(v) }: { rows: StackRow[]; label: string; share?: boolean; legend?: { label: string; color: string }[]; format?: (value: number) => string }) {
  const totals = rows.map((r) => r.parts.reduce((sum, p) => sum + p.value, 0))
  const top = Math.max(1, ...totals)
  return (
    <>
      <PlotBox min={rows.length * 30 + 8}>
        {(width, height) => {
          const names = labelColumn(rows.map((r) => r.label), width)
          const after = Math.max(30, ...rows.map((r, i) => textWidth(r.note ?? format(totals[i])) + 12))
          const span = Math.max(30, width - names.room - after)
          const { row, start, bar } = rowLayout(rows.length, height)
          return (
            <svg className="chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
              {rows.map((item, index) => {
                const y = start + index * row + row / 2
                const scale = span / (share ? totals[index] || 1 : top)
                let x = names.room
                return (
                  <g key={item.key}>
                    <text x={names.room - 8} y={y + 4} textAnchor="end" className="chart-label">
                      <title>{item.label}</title>
                      {names.fit(item.label)}
                    </text>
                    {item.parts.map((part, partIndex) => {
                      const size = part.value * scale
                      const rect = (
                        <rect key={`${part.key}-${partIndex}`} x={x} y={y - bar / 2} width={Math.max(size - 1, 0)} height={bar} rx={2} fill={part.color}>
                          <title>{`${item.label} · ${part.label ?? part.key}: ${format(part.value)}`}</title>
                        </rect>
                      )
                      x += size
                      return rect
                    })}
                    <text x={x + 6} y={y + 4} className="chart-value">
                      {item.note ?? format(totals[index])}
                    </text>
                  </g>
                )
              })}
            </svg>
          )
        }}
      </PlotBox>
      {legend && <Legend items={legend} />}
    </>
  )
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span key={item.label}>
          <span className="chart-swatch" style={{ background: item.color, borderColor: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

export type BoxRow = { key: number | string; label: string; color: string; q1: number; q3: number; median: number; low: number; high: number; outliers: number[]; note?: string }

/** Box plots: the box holds the middle half of the values, and the line in it is the median. */
export function BoxChart({ rows, format, label }: { rows: BoxRow[]; format: (value: number) => string; label: string }) {
  return (
    <PlotBox min={rows.length * 34 + 34}>
      {(width, height) => {
        const names = labelColumn(rows.map((r) => r.label), width)
        const after = Math.max(...rows.map((r) => textWidth(r.note ?? format(r.median)) + 16))
        const bottom = 28
        const low = Math.min(...rows.flatMap((r) => [r.low, ...r.outliers]))
        const high = Math.max(...rows.flatMap((r) => [r.high, ...r.outliers]))
        const end = width - after
        const px = (v: number) => names.room + ((v - low) / (high - low || 1)) * Math.max(30, end - names.room - 10)
        const ticks: number[] = []
        const step = niceStep(high - low || 1, Math.max(2, (end - names.room) / 90))
        for (let v = Math.ceil(low / step) * step; v <= high; v += step) ticks.push(v)
        const { row, start } = rowLayout(rows.length, height, 4, bottom, 60)
        return (
          <svg className="chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
            {ticks.map((v) => (
              <g key={v}>
                <line x1={px(v)} x2={px(v)} y1={4} y2={height - bottom} className="chart-grid-line" />
                <text x={px(v)} y={height - 8} textAnchor="middle" className="chart-axis">
                  {format(v)}
                </text>
              </g>
            ))}
            {rows.map((item, index) => {
              const y = start + index * row + row / 2
              return (
                <g key={item.key}>
                  <text x={names.room - 8} y={y + 4} textAnchor="end" className="chart-label">
                    <title>{item.label}</title>
                    {names.fit(item.label)}
                  </text>
                  <line x1={px(item.low)} x2={px(item.high)} y1={y} y2={y} stroke={item.color} />
                  <rect x={px(item.q1)} y={y - 10} width={Math.max(px(item.q3) - px(item.q1), 1)} height={20} fill={item.color} fillOpacity={0.3} stroke={item.color}>
                    <title>{`${item.label}: ${format(item.median)}`}</title>
                  </rect>
                  <line x1={px(item.median)} x2={px(item.median)} y1={y - 10} y2={y + 10} stroke={item.color} strokeWidth={3} />
                  {item.outliers.map((v, i) => (
                    <circle key={i} cx={px(v)} cy={y} r={3} fill="none" stroke={item.color} />
                  ))}
                  <text x={width - after + 8} y={y + 4} className="chart-value">
                    {item.note ?? format(item.median)}
                  </text>
                </g>
              )
            })}
          </svg>
        )
      }}
    </PlotBox>
  )
}

export type HeatCell = { value: number | null; text?: string; mark?: string; title?: string }

/** A table of colors. Low values are green and high values are red, unless "reverse" is set. */
export function HeatMap({ rows, columns, label, reverse = false, low, high }: { rows: { key: number | string; label: string; cells: HeatCell[] }[]; columns: string[]; label: string; reverse?: boolean; low?: number; high?: number }) {
  const values = rows.flatMap((r) => r.cells.map((c) => c.value)).filter((v): v is number => v !== null)
  const [min, max] = [low ?? Math.min(...values), high ?? Math.max(...values)]
  const color = (v: number) => {
    const share = Math.max(0, Math.min(1, (v - min) / (max - min || 1)))
    const hue = (reverse ? share : 1 - share) * 130
    return `hsl(${hue} 70% 36%)`
  }
  const top = 22
  const longest = Math.max(1, ...rows.flatMap((r) => r.cells.map((c) => (c.mark ?? c.text ?? '').length)))
  return (
    <PlotBox min={rows.length * 28 + top}>
      {(width, height) => {
        const names = labelColumn(rows.map((r) => r.label), width)
        const smallest = Math.max(24, textWidth('x'.repeat(longest), 11) + 8)
        // A long race scrolls to the side, and a short one fills the box.
        const cell = Math.max(smallest, (width - names.room) / Math.max(columns.length, 1))
        const inner = Math.max(width, names.room + cell * columns.length)
        const row = Math.min(44, (height - top) / Math.max(rows.length, 1))
        return (
          <div className="chart-scroll">
            <svg className="chart" width={inner} height={row * rows.length + top} viewBox={`0 0 ${inner} ${row * rows.length + top}`} role="img" aria-label={label}>
              {columns.map((name, index) => (
                <text key={index} x={names.room + index * cell + cell / 2} y={14} textAnchor="middle" className="chart-axis">
                  {name}
                </text>
              ))}
              {rows.map((item, r) => (
                <g key={item.key}>
                  <text x={names.room - 8} y={top + r * row + row / 2 + 4} textAnchor="end" className="chart-label">
                    <title>{item.label}</title>
                    {names.fit(item.label)}
                  </text>
                  {item.cells.map((c, index) => (
                    <g key={index}>
                      <rect x={names.room + index * cell} y={top + r * row} width={cell - 2} height={row - 2} rx={2} fill={c.value === null ? 'var(--surface-3)' : color(c.value)}>
                        <title>{c.title ?? ''}</title>
                      </rect>
                      {(c.mark ?? c.text) && (
                        <text x={names.room + index * cell + cell / 2 - 1} y={top + r * row + row / 2 + 3} textAnchor="middle" className="chart-cell">
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
      }}
    </PlotBox>
  )
}

export type ScatterPoint = { key: number | string; label: string; x: number; y: number; color: string; strong?: boolean }

/** Points with a name. A name goes to a free side of its point, so names do not cover names. */
export function ScatterChart({ points, xLabel, yLabel, formatX = String, formatY = String, invertY = false, diagonal = false, labels = true, height = 340 }: { points: ScatterPoint[]; xLabel: string; yLabel: string; formatX?: (v: number) => string; formatY?: (v: number) => string; invertY?: boolean; diagonal?: boolean; labels?: boolean; height?: number }) {
  return (
    <PlotBox min={height}>
      {(width, boxHeight) => {
        const range = (values: number[]) => {
          const [a, b] = [Math.min(...values), Math.max(...values)]
          const margin = (b - a || 1) * 0.1
          return [a - margin, b + margin]
        }
        const [minX, maxX] = range(points.map((p) => p.x))
        const [minY, maxY] = range(points.map((p) => p.y))
        const ticks = (a: number, b: number, count: number) => {
          const step = niceStep(b - a, count)
          const out: number[] = []
          for (let v = Math.ceil(a / step) * step; v <= b; v += step) out.push(v)
          return out
        }
        const ticksY = ticks(minY, maxY, Math.max(3, boxHeight / 60))
        const pad = { left: 34 + Math.max(24, ...ticksY.map((v) => textWidth(formatY(v)))), right: 16, top: 14, bottom: 44 }
        const px = (v: number) => pad.left + ((v - minX) / (maxX - minX)) * (width - pad.left - pad.right)
        const py = (v: number) => {
          const share = (v - minY) / (maxY - minY)
          return pad.top + (invertY ? share : 1 - share) * (boxHeight - pad.top - pad.bottom)
        }
        const taken: { x1: number; x2: number; y1: number; y2: number }[] = points.map((p) => ({ x1: px(p.x) - 8, x2: px(p.x) + 8, y1: py(p.y) - 8, y2: py(p.y) + 8 }))
        const place = (p: ScatterPoint) => {
          const w = textWidth(p.label)
          const [cx, cy] = [px(p.x), py(p.y)]
          const options = [
            { x: cx + 10, y: cy + 4, anchor: 'start' },
            { x: cx - 10, y: cy + 4, anchor: 'end' },
            { x: cx, y: cy - 12, anchor: 'middle' },
            { x: cx, y: cy + 20, anchor: 'middle' },
            { x: cx + 10, y: cy - 10, anchor: 'start' },
            { x: cx - 10, y: cy + 18, anchor: 'end' },
          ]
          const fits = (o: (typeof options)[number]) => {
            const x1 = o.anchor === 'start' ? o.x : o.anchor === 'end' ? o.x - w : o.x - w / 2
            const box = { x1, x2: x1 + w, y1: o.y - 11, y2: o.y + 3 }
            if (box.x1 < pad.left || box.x2 > width || box.y1 < 0 || box.y2 > boxHeight - pad.bottom) return null
            return taken.some((t) => box.x1 < t.x2 && box.x2 > t.x1 && box.y1 < t.y2 && box.y2 > t.y1) ? null : box
          }
          for (const option of options) {
            const box = fits(option)
            if (box) {
              taken.push(box)
              return option
            }
          }
          return null // The point keeps its name in the tooltip.
        }
        return (
          <svg className="chart" width={width} height={boxHeight} viewBox={`0 0 ${width} ${boxHeight}`} role="img" aria-label={`${xLabel} / ${yLabel}`}>
            {ticksY.map((v) => (
              <g key={v}>
                <line x1={pad.left} x2={width - pad.right} y1={py(v)} y2={py(v)} className="chart-grid-line" />
                <text x={pad.left - 8} y={py(v) + 4} textAnchor="end" className="chart-axis">
                  {formatY(v)}
                </text>
              </g>
            ))}
            {ticks(minX, maxX, Math.max(2, width / 90)).map((v) => (
              <text key={v} x={px(v)} y={boxHeight - 24} textAnchor="middle" className="chart-axis">
                {formatX(v)}
              </text>
            ))}
            <text x={(width + pad.left - pad.right) / 2} y={boxHeight - 6} textAnchor="middle" className="chart-axis">
              {xLabel}
            </text>
            <text x={14} y={boxHeight / 2} transform={`rotate(-90 14 ${boxHeight / 2})`} textAnchor="middle" className="chart-axis">
              {yLabel}
            </text>
            {diagonal && <line x1={px(Math.max(minX, minY))} y1={py(Math.max(minX, minY))} x2={px(Math.min(maxX, maxY))} y2={py(Math.min(maxX, maxY))} className="chart-zero" />}
            {points.map((p) => {
              const spot = labels ? place(p) : null
              return (
                <g key={p.key}>
                  <circle cx={px(p.x)} cy={py(p.y)} r={labels ? (p.strong ? 8 : 5.5) : 1.6} fill={p.color} stroke={p.strong && labels ? 'var(--ink)' : 'none'} strokeWidth={2}>
                    {labels && <title>{`${p.label}: ${formatX(p.x)} · ${formatY(p.y)}`}</title>}
                  </circle>
                  {spot && (
                    <text x={spot.x} y={spot.y} textAnchor={spot.anchor as 'start' | 'end' | 'middle'} className="chart-value">
                      {p.label}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        )
      }}
    </PlotBox>
  )
}

/** A radar graph of scores from 0 to 100. */
export function RadarChart({ axes, series, label }: { axes: string[]; series: { key: number | string; label: string; color: string; values: (number | null)[]; dashed?: boolean }[]; label: string }) {
  return (
    <>
      <PlotBox min={320}>
        {(width, height) => {
          const room = Math.max(...axes.map((a) => textWidth(a)))
          const radius = Math.max(50, Math.min(width / 2 - room - 12, height / 2 - 26))
          const at = (index: number, value: number): [number, number] => {
            const angle = (Math.PI * 2 * index) / axes.length - Math.PI / 2
            return [width / 2 + (Math.cos(angle) * radius * value) / 100, height / 2 + (Math.sin(angle) * radius * value) / 100]
          }
          return (
            <svg className="chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
              {[25, 50, 75, 100].map((ring) => (
                <polygon key={ring} points={axes.map((_, i) => at(i, ring).join(',')).join(' ')} fill="none" className="chart-grid-line" />
              ))}
              {axes.map((name, index) => {
                const [x, y] = at(index, 100)
                const [tx, ty] = at(index, 108)
                const side = tx < width / 2 - 4 ? 'end' : tx > width / 2 + 4 ? 'start' : 'middle'
                return (
                  <g key={name}>
                    <line x1={width / 2} y1={height / 2} x2={x} y2={y} className="chart-grid-line" />
                    <text x={tx} y={ty + 4} textAnchor={side} className="chart-axis">
                      {name}
                    </text>
                  </g>
                )
              })}
              {series.map((s) => (
                <polygon key={s.key} points={s.values.map((v, i) => at(i, v ?? 0).join(',')).join(' ')} fill={s.color} fillOpacity={0.2} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '5 4' : undefined}>
                  <title>{`${s.label}: ${s.values.map((v, i) => `${axes[i]} ${v ?? '—'}`).join(' · ')}`}</title>
                </polygon>
              ))}
            </svg>
          )
        }}
      </PlotBox>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
    </>
  )
}

/** Drivers on a circle, and a line for each pair. A thick line is a pair with many battles. */
export function NetworkChart({ nodes, edges, label }: { nodes: { id: number; label: string; color: string }[]; edges: { a: number; b: number; weight: number; title: string }[]; label: string }) {
  return (
    <PlotBox min={340}>
      {(width, height) => {
        const room = Math.max(40, ...nodes.map((n) => textWidth(n.label)))
        const radius = Math.max(50, Math.min(width / 2 - room - 16, height / 2 - 26))
        const at = (index: number): [number, number] => {
          const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2
          return [width / 2 + Math.cos(angle) * radius, height / 2 + Math.sin(angle) * radius]
        }
        const heaviest = Math.max(1, ...edges.map((e) => e.weight))
        const place = new Map(nodes.map((n, i) => [n.id, at(i)]))
        return (
          <svg className="chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
            {edges.map((edge) => {
              const [a, b] = [place.get(edge.a), place.get(edge.b)]
              if (!a || !b) return null
              return (
                <line key={`${edge.a}-${edge.b}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--ink-2)" strokeOpacity={0.3 + (0.6 * edge.weight) / heaviest} strokeWidth={1 + (6 * edge.weight) / heaviest}>
                  <title>{edge.title}</title>
                </line>
              )
            })}
            {nodes.map((node, index) => {
              const [x, y] = at(index)
              const side = x < width / 2 - 4 ? 'end' : x > width / 2 + 4 ? 'start' : 'middle'
              return (
                <g key={node.id}>
                  <circle cx={x} cy={y} r={7} fill={node.color} />
                  <text x={x + (side === 'end' ? -11 : side === 'start' ? 11 : 0)} y={y + (side === 'middle' ? (y < height / 2 ? -11 : 20) : 4)} textAnchor={side} className="chart-label">
                    {node.label}
                  </text>
                </g>
              )
            })}
          </svg>
        )
      }}
    </PlotBox>
  )
}
