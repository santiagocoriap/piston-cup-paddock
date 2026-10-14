import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { useLoad } from '../lib/useLoad'
import { TabEmpty } from './TabEmpty'

type Car = components['schemas']['CarTrackOut']

const COLORS = ['#e10600', '#38bdf8', '#facc15', '#4ade80', '#c084fc', '#fb923c', '#f472b6', '#a3a3a3']
/** Between two samples less than this far apart, the dot moves in a straight line. */
export const MAX_GAP_MS = 1000
const SPEEDS = [1, 2, 4, 8, 16]

/** The position of a car at a time, or null in a gap. */
export function positionAt(car: Car, t: number): { x: number; z: number } | null {
  const times = car.t_ms
  if (times.length === 0 || t < times[0] || t > times[times.length - 1]) return null
  let low = 0
  let high = times.length - 1
  while (high - low > 1) {
    const middle = (low + high) >> 1
    if (times[middle] <= t) low = middle
    else high = middle
  }
  if (times[low] === t || low === high) return { x: car.x[low], z: car.z[low] }
  if (times[high] - times[low] > MAX_GAP_MS) return null
  const share = (t - times[low]) / (times[high] - times[low])
  return { x: car.x[low] + (car.x[high] - car.x[low]) * share, z: car.z[low] + (car.z[high] - car.z[low]) * share }
}

function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/** A simplified replay: dots move from the recorded positions. It is not an AC replay. */
export function ReplaySection({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const [attempt, setAttempt] = useState<number | null>(null)
  const load = useLoad(
    () =>
      api.GET('/api/rounds/{round_id}/replay', {
        params: { path: { round_id: roundId }, query: attempt ? { attempt } : {} },
      }),
    [roundId, attempt],
  )
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(4)
  const last = useRef<number | null>(null)
  const data = load.data
  const duration = data?.duration_ms ?? 0

  useEffect(() => {
    if (!playing) return
    let frame = 0
    const step = (now: number) => {
      const before = last.current ?? now
      last.current = now
      setTime((value) => {
        const next = value + (now - before) * speed
        if (next >= duration) {
          setPlaying(false)
          return duration
        }
        return next
      })
      frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(frame)
      last.current = null
    }
  }, [playing, speed, duration])

  if (!data) return null
  if (!data.has_positions) {
    return (
      <TabEmpty
        heading={t('replay.title')}
        icon="map"
        title={t('tabEmpty.noPositions')}
        text={t('tabEmpty.replay')}
      />
    )
  }
  const xs = data.cars.flatMap((c) => c.x)
  const zs = data.cars.flatMap((c) => c.z)
  const [minX, maxX, minZ, maxZ] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)]
  const span = Math.max(maxX - minX, maxZ - minZ, 1)
  const size = 400
  const px = (x: number) => 16 + ((x - minX) / span) * (size - 32)
  const pz = (z: number) => 16 + ((z - minZ) / span) * (size - 32)
  const now = data.cars.map((car, index) => ({ car, color: COLORS[index % COLORS.length], at: positionAt(car, time) }))
  const missing = now.filter((item) => !item.at)

  return (
    <section aria-label={t('replay.title')}>
      <h2>{t('replay.title')}</h2>
      <p className="muted">{t('replay.help', { gap: MAX_GAP_MS / 1000 })}</p>
      {data.attempts.length > 1 && (
        <label>
          {t('replay.attempt')}
          <select
            value={data.attempt ?? ''}
            onChange={(e) => {
              setPlaying(false)
              setTime(0)
              setAttempt(Number(e.target.value))
            }}
          >
            {data.attempts.map((a) => (
              <option key={a.number} value={a.number}>
                {t('replay.attemptN', { number: a.number })}
              </option>
            ))}
          </select>
        </label>
      )}
      <figure className="incident-map">
        <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={t('replay.map')}>
          {data.cars.map((car, index) => (
            <polyline
              key={`trail-${car.key}`}
              points={car.x.map((x, i) => `${px(x)},${pz(car.z[i])}`).join(' ')}
              fill="none"
              stroke={COLORS[index % COLORS.length]}
              strokeOpacity={0.12}
            />
          ))}
          {now.map(({ car, color, at }) =>
            at ? <circle key={car.key} cx={px(at.x)} cy={pz(at.z)} r={6} fill={color} stroke="#0a0a0a" /> : null,
          )}
        </svg>
      </figure>
      <div className="replay-controls">
        <button type="button" onClick={() => setPlaying((p) => !p)}>
          {playing ? t('replay.pause') : t('replay.play')}
        </button>
        <label>
          {t('replay.speed')}
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
        <span>
          {clock(time)} / {clock(duration)}
        </span>
      </div>
      <div className="timeline">
        <input
          type="range"
          min={0}
          max={duration}
          step={100}
          value={Math.round(time)}
          onChange={(e) => setTime(Number(e.target.value))}
          aria-label={t('replay.timeline')}
        />
        {data.markers.map((marker) => (
          <button
            key={`${marker.kind}-${marker.t_ms}`}
            type="button"
            className={`marker-tick ${marker.kind}`}
            style={{ left: `${(marker.t_ms / Math.max(duration, 1)) * 100}%` }}
            title={marker.kind === 'incident' ? t('replay.incident', { cars: marker.label }) : t('replay.restart')}
            aria-label={marker.kind === 'incident' ? t('replay.incident', { cars: marker.label }) : t('replay.restart')}
            onClick={() => setTime(marker.t_ms)}
          />
        ))}
      </div>
      <p className="legend">
        {now.map(({ car, color, at }) => (
          <span key={car.key} className="legend-item">
            <span className="swatch" style={{ background: at ? color : 'transparent', border: `1px solid ${color}` }} />
            {car.name}
          </span>
        ))}
      </p>
      {missing.length > 0 && (
        <p className="muted">{t('replay.gap', { names: missing.map((m) => m.car.name).join(', ') })}</p>
      )}
    </section>
  )
}
