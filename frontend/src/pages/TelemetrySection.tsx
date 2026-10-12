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

/** Speed (and pedals with full access) against the track position. */
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
    </figure>
  )
}
