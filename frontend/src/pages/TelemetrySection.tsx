import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type LapDetail = components['schemas']['LapDetailOut']

/** Telemetry laps of the round that the viewer may see. Basic results never need it. */
export function TelemetrySection({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const laps = useLoad(
    () => api.GET('/api/rounds/{round_id}/telemetry', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const [detail, setDetail] = useState<LapDetail | null>(null)
  if (!laps.data || laps.data.length === 0) return null

  async function open(id: number) {
    const { data } = await api.GET('/api/telemetry-laps/{lap_id}', { params: { path: { lap_id: id } } })
    if (data) setDetail(data)
  }

  return (
    <section aria-label={t('telemetry.roundTitle')}>
      <h2>{t('telemetry.roundTitle')}</h2>
      <ul className="list">
        {laps.data.map((lap) => (
          <li key={lap.id}>
            <button type="button" className="link-button" onClick={() => open(lap.id)}>
              {lap.driver_name} · {t('laps.lapNumber', { number: lap.lap_number })} · {formatLapTime(lap.lap_time_ms)}
            </button>{' '}
            <span className="badge">{t(`telemetry.access.${lap.access}`)}</span>
          </li>
        ))}
      </ul>
      {detail && <TraceChart lap={detail} />}
    </section>
  )
}

/** Speed against the track position. With full access: pedals, steering, and gear too. */
function TraceChart({ lap }: { lap: LapDetail }) {
  const { t } = useTranslation()
  const pos = lap.channels.pos ?? []
  const speed = lap.channels.speed_kmh ?? []
  if (pos.length < 2) return null
  const width = 640
  const height = 200
  const top = Math.max(...speed, 1)
  const x = (p: number) => 8 + p * (width - 16)
  const line = (values: number[], max: number) =>
    values.map((v, i) => `${x(pos[i])},${height - 8 - (v / max) * (height - 16)}`).join(' ')
  return (
    <figure className="lap-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t('telemetry.chart', { name: lap.driver_name })}>
        <polyline points={line(speed, top)} fill="none" stroke="#38bdf8" strokeWidth={2} />
        {lap.channels.gas && <polyline points={line(lap.channels.gas, 1)} fill="none" stroke="#4ade80" strokeWidth={1} />}
        {lap.channels.brake && <polyline points={line(lap.channels.brake, 1)} fill="none" stroke="#e10600" strokeWidth={1} />}
      </svg>
      <figcaption>
        {lap.driver_name} · {t('laps.lapNumber', { number: lap.lap_number })} · {t('telemetry.speed', { max: Math.round(top) })}
        {lap.access === 'full' ? ` · ${t('telemetry.pedals')}` : ` · ${t('telemetry.noInputs')}`}
      </figcaption>
      {lap.channels.steer && <SteerChart pos={pos} steer={lap.channels.steer} name={lap.driver_name} />}
      {lap.channels.gear && <GearChart pos={pos} gear={lap.channels.gear} name={lap.driver_name} />}
    </figure>
  )
}

const WIDTH = 640
const SMALL = 90
const px = (p: number) => 8 + p * (WIDTH - 16)

/** Steering against the track position. The middle line is straight ahead. */
function SteerChart({ pos, steer, name }: { pos: number[]; steer: number[]; name: string }) {
  const { t } = useTranslation()
  const top = Math.max(...steer.map(Math.abs), 0.01)
  const middle = SMALL / 2
  const points = steer.map((v, i) => `${px(pos[i])},${middle - (v / top) * (middle - 6)}`).join(' ')
  return (
    <>
      <svg viewBox={`0 0 ${WIDTH} ${SMALL}`} role="img" aria-label={t('telemetry.steerChart', { name })}>
        <line x1={8} x2={WIDTH - 8} y1={middle} y2={middle} stroke="currentColor" strokeOpacity={0.3} />
        <polyline points={points} fill="none" stroke="#fbbf24" strokeWidth={1.5} />
      </svg>
      <figcaption>{t('telemetry.steer')}</figcaption>
    </>
  )
}

/** The gear against the track position, as steps. */
function GearChart({ pos, gear, name }: { pos: number[]; gear: number[]; name: string }) {
  const { t } = useTranslation()
  const top = Math.max(...gear, 1)
  const y = (g: number) => SMALL - 6 - (Math.max(g, 0) / top) * (SMALL - 12)
  const points = gear.flatMap((g, i) => (i === 0 ? [`${px(pos[0])},${y(g)}`] : [`${px(pos[i])},${y(gear[i - 1])}`, `${px(pos[i])},${y(g)}`])).join(' ')
  return (
    <>
      <svg viewBox={`0 0 ${WIDTH} ${SMALL}`} role="img" aria-label={t('telemetry.gearChart', { name })}>
        <polyline points={points} fill="none" stroke="#c084fc" strokeWidth={1.5} />
      </svg>
      <figcaption>{t('telemetry.gear', { max: top })}</figcaption>
    </>
  )
}
