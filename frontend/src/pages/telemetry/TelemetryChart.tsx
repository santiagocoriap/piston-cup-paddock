import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export type LaneDef = {
  key: string
  label: string
  unit: string
  height: number
  digits: number
  step?: boolean
  zero?: boolean
  range?: [number, number]
}
export type Lane = { def: LaneDef; values: (number | null)[][] }
export type SeriesDef = { label: string; color: string }
export type View = [number, number]

const SYNC = 'paddock-telemetry'
const AXIS = 58
const MIN_SPAN = 0.004

/** The lanes of the telemetry, one under the other, on the same lap distance. All lanes zoom,
 * move, and show the cursor together. */
export function TelemetryChart({
  x,
  xLabel,
  lanes,
  series,
  view,
  onView,
  cursor,
  onCursor,
  overview,
}: {
  x: number[]
  xLabel: (value: number) => string
  lanes: Lane[]
  series: SeriesDef[]
  view: View
  onView: (view: View) => void
  cursor: number | null
  onCursor: (index: number | null) => void
  overview: (number | null)[]
}) {
  const box = useRef<HTMLDivElement>(null)
  const holders = useRef<(HTMLDivElement | null)[]>([])
  const plots = useRef<uPlot[]>([])
  const applying = useRef(false)
  const fromChart = useRef(false)
  const viewRef = useRef(view)
  const [width, setWidth] = useState(0)
  const [hovered, setHovered] = useState<number | null>(null)
  // The drawing area of the plots, so that the overview bar lines up with it.
  const [area, setArea] = useState({ left: AXIS, width: 0 })
  const callbacks = useRef({ onView, onCursor })
  callbacks.current = { onView, onCursor }
  viewRef.current = view

  useLayoutEffect(() => {
    const element = box.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(Math.floor(element.clientWidth)))
    observer.observe(element)
    setWidth(Math.floor(element.clientWidth))
    return () => observer.disconnect()
  }, [])

  // The full lap, for the limits of the zoom.
  const full: View = [x[0], x[x.length - 1]]

  useEffect(() => {
    if (width === 0) return
    let frame = 0
    const clamp = ([a, b]: View): View => {
      const span = Math.max(b - a, (full[1] - full[0]) * MIN_SPAN)
      let min = Math.max(full[0], a)
      let max = min + span
      if (max > full[1]) {
        max = full[1]
        min = Math.max(full[0], max - span)
      }
      return [min, max]
    }
    const made = lanes.map((lane, index) => {
      const last = index === lanes.length - 1
      const opts: uPlot.Options = {
        width,
        height: lane.def.height + (last ? 34 : 0),
        legend: { show: false },
        cursor: {
          sync: { key: SYNC, setSeries: false },
          drag: { x: true, y: false, setScale: true },
          points: { size: 7, width: 2 },
          bind: {
            // Shift and drag (or the middle button) moves the view. A plain drag picks a part.
            mousedown: (u, _target, handler) => (event: MouseEvent) => {
              if (!event.shiftKey && event.button !== 1) return handler(event)
              event.preventDefault()
              const startX = event.clientX
              const [a, b] = [u.scales.x.min ?? full[0], u.scales.x.max ?? full[1]]
              const perPixel = (b - a) / u.over.clientWidth
              const move = (e: MouseEvent) => {
                const shift = (startX - e.clientX) * perPixel
                callbacks.current.onView(clamp([a + shift, b + shift]))
              }
              const up = () => {
                window.removeEventListener('mousemove', move)
                window.removeEventListener('mouseup', up)
              }
              window.addEventListener('mousemove', move)
              window.addEventListener('mouseup', up)
              return null
            },
          },
        },
        select: { show: true, left: 0, top: 0, width: 0, height: 0 },
        scales: {
          x: { time: false },
          y: lane.def.range
            ? { range: lane.def.range }
            : {
                range: (_u, min, max) => {
                  if (lane.def.zero) {
                    const edge = Math.max(Math.abs(min), Math.abs(max), 0.05) * 1.1
                    return [-edge, edge]
                  }
                  const pad = (max - min) * 0.08 || 1
                  return [min - pad, max + pad]
                },
              },
        },
        axes: [
          {
            show: true,
            size: last ? 34 : 0,
            stroke: '#a3a3a3',
            font: '12px system-ui, sans-serif',
            grid: { stroke: 'rgba(255,255,255,0.07)', width: 1 },
            ticks: { show: last, stroke: 'rgba(255,255,255,0.2)' },
            values: last ? (_u, splits) => splits.map(xLabel) : () => [],
          },
          {
            size: AXIS,
            stroke: '#a3a3a3',
            font: '12px system-ui, sans-serif',
            grid: { stroke: 'rgba(255,255,255,0.07)', width: 1 },
            ticks: { stroke: 'rgba(255,255,255,0.2)' },
            values: (_u, splits) => splits.map((v) => v.toFixed(lane.def.digits)),
          },
        ],
        series: [
          {},
          ...series.map((s) => ({
            label: s.label,
            stroke: s.color,
            width: 1.6,
            spanGaps: false,
            paths: lane.def.step ? uPlot.paths.stepped!({ align: 1 }) : undefined,
            points: { show: false },
          })),
        ],
        hooks: {
          setScale: [
            (u, key) => {
              if (key !== 'x' || applying.current) return
              const [a, b] = [u.scales.x.min ?? full[0], u.scales.x.max ?? full[1]]
              const [va, vb] = viewRef.current
              if (Math.abs(a - va) > 1e-9 || Math.abs(b - vb) > 1e-9) callbacks.current.onView(clamp([a, b]))
            },
          ],
          setCursor: [
            (u) => {
              cancelAnimationFrame(frame)
              const idx = u.cursor.idx
              frame = requestAnimationFrame(() => {
                fromChart.current = true
                callbacks.current.onCursor(idx ?? null)
              })
            },
          ],
          draw: [
            (u) => {
              if (!lane.def.zero) return
              // The zero line of the delta: on it, the lap is level with the reference.
              const y = Math.round(u.valToPos(0, 'y', true))
              const ctx = u.ctx
              ctx.save()
              ctx.strokeStyle = 'rgba(255,255,255,0.45)'
              ctx.lineWidth = 1
              ctx.beginPath()
              ctx.moveTo(u.bbox.left, y)
              ctx.lineTo(u.bbox.left + u.bbox.width, y)
              ctx.stroke()
              ctx.restore()
            },
          ],
        },
      }
      const data = [x, ...lane.values] as uPlot.AlignedData
      const plot = new uPlot(opts, data, holders.current[index]!)
      plot.over.addEventListener(
        'wheel',
        (event: WheelEvent) => {
          event.preventDefault()
          const [a, b] = [plot.scales.x.min ?? full[0], plot.scales.x.max ?? full[1]]
          if (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
            const shift = ((event.deltaX || event.deltaY) > 0 ? 1 : -1) * (b - a) * 0.12
            callbacks.current.onView(clamp([a + shift, b + shift]))
            return
          }
          const at = plot.posToVal(event.offsetX, 'x')
          const factor = event.deltaY < 0 ? 0.8 : 1.25
          callbacks.current.onView(clamp([at - (at - a) * factor, at + (b - at) * factor]))
        },
        { passive: false },
      )
      return plot
    })
    plots.current = made
    setArea({ left: made[0]?.over.offsetLeft ?? AXIS, width: made[0]?.over.clientWidth ?? 0 })
    applying.current = true
    made.forEach((plot) => plot.setScale('x', { min: viewRef.current[0], max: viewRef.current[1] }))
    applying.current = false
    return () => {
      cancelAnimationFrame(frame)
      made.forEach((plot) => plot.destroy())
      plots.current = []
    }
    // The plots are made again when the data or the size changes. The view and the cursor
    // change without a new plot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [x, lanes, series, width])

  useEffect(() => {
    applying.current = true
    plots.current.forEach((plot) => {
      if (plot.scales.x.min !== view[0] || plot.scales.x.max !== view[1]) plot.setScale('x', { min: view[0], max: view[1] })
    })
    applying.current = false
  }, [view])

  // A cursor from outside the chart (the track map) moves the chart cursor.
  useEffect(() => {
    if (fromChart.current) {
      fromChart.current = false
      return
    }
    const plot = plots.current[0]
    if (!plot) return
    if (cursor === null) {
      plot.setCursor({ left: -10, top: -10 })
      return
    }
    plot.setCursor({ left: plot.valToPos(x[cursor], 'x'), top: plot.bbox.height / devicePixelRatio / 2 })
  }, [cursor, x])

  const first = plots.current[0]
  // The cursor place in the lane, from the left side of the lane.
  const left = cursor !== null && first ? first.over.offsetLeft + first.valToPos(x[cursor], 'x') : null

  return (
    <div className="tm-chart" ref={box}>
      {lanes.map((lane, index) => (
        <div
          key={lane.def.key}
          className="tm-lane"
          onMouseEnter={() => setHovered(index)}
          onMouseLeave={() => setHovered((h) => (h === index ? null : h))}
        >
          <span className="tm-lane-label">
            {lane.def.label}
            {lane.def.unit && <small> {lane.def.unit}</small>}
          </span>
          <div ref={(element) => void (holders.current[index] = element)} />
          {hovered === index && cursor !== null && left !== null && (
            <div className={left > width * 0.6 ? 'tm-tip left' : 'tm-tip'} style={{ left }}>
              <b>{xLabel(x[cursor])}</b>
              {series.map((s, i) => {
                const value = lane.values[i]?.[cursor]
                return (
                  <span key={s.label} className="tm-tip-row">
                    <i style={{ background: s.color }} aria-hidden="true" />
                    {s.label}
                    <b>
                      {value === null || value === undefined
                        ? '—'
                        : `${lane.def.zero && value > 0 ? '+' : ''}${value.toFixed(lane.def.digits)} ${lane.def.unit}`}
                    </b>
                  </span>
                )
              })}
            </div>
          )}
        </div>
      ))}
      <Overview x={x} values={overview} view={view} onView={onView} full={full} area={area} />
    </div>
  )
}

/** The whole lap in a thin bar, with the part on screen as a window. Drag the window to move
 * the view. A click centers the view there. */
function Overview({
  x,
  values,
  view,
  onView,
  full,
  area,
}: {
  x: number[]
  values: (number | null)[]
  view: View
  onView: (view: View) => void
  full: View
  area: { left: number; width: number }
}) {
  const inner = Math.max(area.width, 1)
  const span = full[1] - full[0] || 1
  const px = (v: number) => ((v - full[0]) / span) * inner
  const numbers = values.filter((v): v is number => v !== null)
  const [low, high] = [Math.min(...numbers, 0), Math.max(...numbers, 1)]
  const points = values
    .map((v, i) => (v === null ? null : `${px(x[i]).toFixed(1)},${(30 - ((v - low) / (high - low || 1)) * 26).toFixed(1)}`))
    .filter(Boolean)
    .join(' ')

  function drag(event: ReactPointerEvent<HTMLDivElement>) {
    const bar = event.currentTarget.getBoundingClientRect()
    const size = view[1] - view[0]
    const toValue = (clientX: number) => full[0] + ((clientX - bar.left) / bar.width) * span
    const inside = toValue(event.clientX) >= view[0] && toValue(event.clientX) <= view[1]
    const grab = inside ? toValue(event.clientX) - view[0] : size / 2
    const place = (clientX: number) => {
      const min = Math.min(Math.max(full[0], toValue(clientX) - grab), full[1] - size)
      onView([min, min + size])
    }
    place(event.clientX)
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)
    const move = (e: PointerEvent) => place(e.clientX)
    const up = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', up)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', up)
  }

  return (
    <div className="tm-overview" style={{ marginLeft: area.left, width: inner }} onPointerDown={drag}>
      <svg viewBox={`0 0 ${inner} 32`} preserveAspectRatio="none" aria-hidden="true">
        <polyline points={points} />
      </svg>
      <span className="tm-window" style={{ left: px(view[0]), width: Math.max(px(view[1]) - px(view[0]), 4) }} />
    </div>
  )
}
