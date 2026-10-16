import { useTranslation } from 'react-i18next'
import { fit, type Point } from '../../lib/trackMap'
import { pointAt } from '../../lib/telemetryMath'

type TrackMap = { spline: number[]; x: number[]; z: number[] }

const SIZE = 400

/** The track, with the part of the lap on the chart in color and a dot at the cursor. With 2 or
 * more laps, each part of the track has the color of the lap that is fastest there. Move the
 * mouse on the track to move the chart cursor. A click zooms the chart to that corner. */
export function TelemetryMap({
  map,
  view,
  cursor,
  fastest,
  colors,
  onHover,
  onPick,
}: {
  map: TrackMap
  view: [number, number] // As lap distance, 0 to 1.
  cursor: number | null // As lap distance, 0 to 1.
  fastest: (number | null)[] // The fastest lap index of each part of the track.
  colors: string[]
  onHover: (s: number | null) => void
  onPick: (s: number) => void
}) {
  const { t } = useTranslation()
  const points: Point[] = map.x.map((x, i) => ({ x, z: map.z[i] }))
  if (points.length < 10) return <p className="muted tm-map-empty">{t('telemetryTool.noMap')}</p>
  const place = fit(points, SIZE, 18)
  const line = (from: number, to: number) =>
    map.spline
      .map((s, i) => (s >= from && s <= to ? place(points[i]).join(',') : null))
      .filter(Boolean)
      .join(' ')
  const parts = fastest.length
  const dot = cursor !== null ? pointAt(map, cursor) : null

  /** The lap distance of the track point nearest to the mouse. */
  function nearest(event: React.MouseEvent<SVGSVGElement>): number | null {
    const svg = event.currentTarget
    const box = svg.getBoundingClientRect()
    const mx = ((event.clientX - box.left) / box.width) * SIZE
    const my = ((event.clientY - box.top) / box.height) * SIZE
    let best = -1
    let bestDistance = Infinity
    points.forEach((p, i) => {
      const [px, py] = place(p)
      const distance = (px - mx) ** 2 + (py - my) ** 2
      if (distance < bestDistance) {
        bestDistance = distance
        best = i
      }
    })
    return best >= 0 && bestDistance < 30 ** 2 ? map.spline[best] : null
  }

  return (
    <figure className="tm-map">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={t('telemetryTool.map')}
        onMouseMove={(event) => onHover(nearest(event))}
        onMouseLeave={() => onHover(null)}
        onClick={(event) => {
          const s = nearest(event)
          if (s !== null) onPick(s)
        }}
      >
        <polyline className="tm-track" points={line(0, 1)} />
        {parts > 0
          ? fastest.map((lap, part) =>
              lap === null ? null : (
                <polyline
                  key={part}
                  className="tm-part"
                  stroke={colors[lap]}
                  points={line(part / parts, (part + 1) / parts + 0.002)}
                />
              ),
            )
          : null}
        <polyline className="tm-view" points={line(view[0], view[1])} />
        {(() => {
          const start = pointAt(map, 0)
          if (!start) return null
          const [sx, sy] = place(start)
          return <rect className="tm-start" x={sx - 6} y={sy - 6} width={12} height={12} rx={2} />
        })()}
        {dot &&
          (() => {
            const [cx, cy] = place(dot)
            return (
              <>
                <circle className="tm-dot-ring" cx={cx} cy={cy} r={13} />
                <circle className="tm-dot" cx={cx} cy={cy} r={6} />
              </>
            )
          })()}
      </svg>
      <figcaption className="muted">{t(parts > 0 ? 'telemetryTool.mapHelpCompare' : 'telemetryTool.mapHelp')}</figcaption>
    </figure>
  )
}
