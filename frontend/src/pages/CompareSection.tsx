import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Comparison = components['schemas']['ComparisonOut']
type Lap = components['schemas']['CompareLapOut']
type Session = 'race' | 'qualifying' | 'practice'

const COLOR_A = '#38bdf8'
const COLOR_B = '#facc15'

function signed(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  const sign = ms > 0 ? '+' : ms < 0 ? '−' : '±'
  return `${sign}${(Math.abs(ms) / 1000).toFixed(3)}`
}

/** Two laps side by side. Lap A is the reference. A positive difference means B is slower. */
export function CompareSection({ roundId, sessions }: { roundId: number; sessions: string[] }) {
  const { t } = useTranslation()
  const [session, setSession] = useState<Session>('race')
  const [pair, setPair] = useState<{ a: number; b: number } | null>(null)
  const result = useLoad(
    () =>
      api.GET('/api/rounds/{round_id}/compare', {
        params: { path: { round_id: roundId }, query: { session, ...(pair ?? {}) } },
      }),
    [roundId, session, pair?.a, pair?.b],
  )
  const data = result.data
  if (!data || sessions.length === 0) return null
  const choose = (side: 'a' | 'b', id: number) => {
    if (!data.a || !data.b) return
    setPair({ a: data.a.id, b: data.b.id, [side]: id })
  }

  return (
    <section aria-label={t('compare.title')}>
      <h2>{t('compare.title')}</h2>
      <div className="tabs" role="tablist">
        {sessions.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={name === session}
            className={name === session ? 'active' : undefined}
            onClick={() => {
              setPair(null)
              setSession(name as Session)
            }}
          >
            {t(`laps.sessions.${name}`)}
          </button>
        ))}
      </div>
      {data.a && data.b ? (
        <>
          <div className="forms">
            <LapPicker label={t('compare.lapA')} lap={data.a} choices={data.choices} onChange={(id) => choose('a', id)} />
            <LapPicker label={t('compare.lapB')} lap={data.b} choices={data.choices} onChange={(id) => choose('b', id)} />
          </div>
          <p className="muted">{t('compare.sign')}</p>
          <Details data={data} a={data.a} b={data.b} />
          <DeltaChart data={data} />
        </>
      ) : (
        <p className="muted">{t('compare.notEnough')}</p>
      )}
      {data.gaps.length > 0 && (
        <ul className="muted">
          {data.gaps.map((gap) => (
            <li key={gap}>{t(`compare.gaps.${gap}`)}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

function LapPicker({ label, lap, choices, onChange }: { label: string; lap: Lap; choices: Lap[]; onChange: (id: number) => void }) {
  const { t } = useTranslation()
  const options = choices.some((c) => c.id === lap.id) ? choices : [lap, ...choices]
  return (
    <label>
      {label}
      <select value={lap.id} onChange={(e) => onChange(Number(e.target.value))}>
        {options.map((choice) => (
          <option key={choice.id} value={choice.id}>
            {choice.driver_name} · {t('laps.lapNumber', { number: choice.lap_number })} · {formatLapTime(choice.lap_time_ms)}
          </option>
        ))}
      </select>
    </label>
  )
}

function Details({ data, a, b }: { data: Comparison; a: Lap; b: Lap }) {
  const { t } = useTranslation()
  const conditions = Object.entries(data.conditions).filter(([, value]) => value !== '' && value !== null)
  const rows: [string, (lap: Lap) => string][] = [
    [t('compare.time'), (lap) => formatLapTime(lap.lap_time_ms)],
    [t('compare.car'), (lap) => lap.car],
    [t('compare.ballast'), (lap) => `${lap.ballast_kg} kg`],
    [t('compare.restrictor'), (lap) => `${lap.restrictor} %`],
    [t('compare.tyre'), (lap) => lap.tyre || '—'],
    [t('compare.telemetry'), (lap) => t(`compare.telemetryLevel.${lap.telemetry}`)],
  ]
  return (
    <div className="table-wrap">
      <table aria-label={t('compare.table')}>
        <thead>
          <tr>
            <th scope="col" />
            <th scope="col" style={{ color: COLOR_A }}>
              A · {a.driver_name} ({t('laps.lapNumber', { number: a.lap_number })})
            </th>
            <th scope="col" style={{ color: COLOR_B }}>
              B · {b.driver_name} ({t('laps.lapNumber', { number: b.lap_number })})
            </th>
            <th scope="col">{t('compare.difference')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, value], index) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              <td>{value(a)}</td>
              <td>{value(b)}</td>
              <td>{index === 0 ? signed(b.lap_time_ms - a.lap_time_ms) : ''}</td>
            </tr>
          ))}
          {data.sector_diff_ms.map((diff, index) => (
            <tr key={`s${index}`}>
              <th scope="row">S{index + 1}</th>
              <td>{formatLapTime(a.sectors_ms[index])}</td>
              <td>{formatLapTime(b.sectors_ms[index])}</td>
              <td className={diff && diff > 0 ? 'slower' : diff && diff < 0 ? 'faster' : undefined}>{signed(diff)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {conditions.length > 0 && (
        <p className="muted">
          {t('compare.conditions')}: {conditions.map(([key, value]) => `${key.replace(/_/g, ' ')} ${value}`).join(' · ')}
        </p>
      )}
    </div>
  )
}

/** The delta along the track, with the zero line. Above zero: B is behind. */
function DeltaChart({ data }: { data: Comparison }) {
  const { t } = useTranslation()
  if (!data.delta) return null
  const { pos, delta_ms: values } = data.delta
  const width = 640
  const height = 200
  const limit = Math.max(1000, ...values.map((v) => Math.abs(v)))
  const x = (p: number) => 8 + p * (width - 16)
  const y = (ms: number) => height / 2 - (ms / limit) * (height / 2 - 12)
  const speedLine = (speed: { pos: number[]; speed_kmh: number[] } | null | undefined) => {
    if (!speed || speed.pos.length < 2) return null
    const top = Math.max(...speed.speed_kmh, 1)
    return speed.pos.map((p, i) => `${x(p)},${height - 4 - (speed.speed_kmh[i] / top) * (height / 3)}`).join(' ')
  }
  const speedA = speedLine(data.speed_a)
  const speedB = speedLine(data.speed_b)
  return (
    <figure className="lap-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t('compare.chart')}>
        <line x1={8} x2={width - 8} y1={y(0)} y2={y(0)} className="grid" />
        <text x={10} y={14} className="axis">
          {t('compare.behind', { value: signed(limit) })}
        </text>
        <text x={10} y={height - 6} className="axis">
          {t('compare.ahead', { value: signed(-limit) })}
        </text>
        {speedA && <polyline points={speedA} fill="none" stroke={COLOR_A} strokeOpacity={0.4} />}
        {speedB && <polyline points={speedB} fill="none" stroke={COLOR_B} strokeOpacity={0.4} />}
        <polyline points={pos.map((p, i) => `${x(p)},${y(values[i])}`).join(' ')} fill="none" stroke="#f5f5f5" strokeWidth={2} />
      </svg>
      <figcaption>
        {t('compare.chartHelp', { coverage: Math.round(data.delta.coverage * 100) })}
      </figcaption>
    </figure>
  )
}
