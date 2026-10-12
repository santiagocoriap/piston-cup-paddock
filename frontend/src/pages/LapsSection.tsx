import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { CompareSection } from './CompareSection'

type RoundLaps = components['schemas']['RoundLapsOut']
type DriverLaps = components['schemas']['DriverLapsOut']
type Average = components['schemas']['AverageOut']
type Session = 'race' | 'qualifying' | 'practice'

const LINE_COLORS = ['#e10600', '#38bdf8', '#facc15', '#4ade80', '#c084fc', '#fb923c', '#f472b6', '#a3a3a3']

/** Lap tables and a lap chart for each session with applied laps. */
export function LapsSection({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const [session, setSession] = useState<Session>('race')
  const laps = useLoad(
    () => api.GET('/api/rounds/{round_id}/laps', { params: { path: { round_id: roundId }, query: { session } } }),
    [roundId, session],
  )
  const data = laps.data
  if (!data || data.sessions.length === 0) return null
  return (
    <section aria-label={t('laps.title')}>
      <h2>{t('laps.title')}</h2>
      <div className="tabs" role="tablist">
        {data.sessions.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={name === session}
            className={name === session ? 'active' : undefined}
            onClick={() => setSession(name as Session)}
          >
            {t(`laps.sessions.${name}`)}
          </button>
        ))}
      </div>
      <Legend data={data} />
      <Summary data={data} />
      <LapChart drivers={data.drivers} />
      {data.drivers.map((driver) => (
        <DriverTable key={driver.entry_id} driver={driver} hasSectors={data.has_sectors} />
      ))}
      <CompareSection roundId={roundId} sessions={data.sessions} />
    </section>
  )
}

function Mark({ mark }: { mark: string | null | undefined }) {
  const { t } = useTranslation()
  if (!mark) return null
  return (
    <span className={`mark ${mark}`} title={t(`laps.marks.${mark}`)} aria-label={t(`laps.marks.${mark}`)}>
      {mark === 'session' ? '◆' : '●'}
    </span>
  )
}

function Legend({ data }: { data: RoundLaps }) {
  const { t } = useTranslation()
  return (
    <p className="muted">
      <span className="mark session">◆</span> {t('laps.marks.session')} · <span className="mark personal">●</span>{' '}
      {t('laps.marks.personal')} · {t('laps.validOnly')}
      {!data.has_pit_data && <> · {t('laps.noPitData')}</>}
      {!data.has_sectors && <> · {t('laps.noSectors')}</>}
    </p>
  )
}

function AverageCell({ average }: { average: Average }) {
  return (
    <>
      {formatLapTime(average.ms)} <span className="muted">({average.laps})</span>
    </>
  )
}

function Summary({ data }: { data: RoundLaps }) {
  const { t } = useTranslation()
  const rules = data.clean_rules.map((rule) => t(`laps.rules.${rule}`)).join(', ')
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('season.driver')}</th>
              <th scope="col">{t('laps.best')}</th>
              <th scope="col">{t('laps.average')}</th>
              <th scope="col">{t('laps.cleanAverage')}</th>
              {data.has_sectors && <th scope="col">{t('laps.theoretical')}</th>}
            </tr>
          </thead>
          <tbody>
            {data.drivers.map((driver) => {
              const best = driver.laps.find((lap) => lap.lap_number === driver.best_lap_number)
              return (
                <tr key={driver.entry_id}>
                  <td>
                    #{driver.number} {driver.driver_name}
                  </td>
                  <td>
                    {formatLapTime(driver.best_lap_ms)} <Mark mark={best?.time_mark} />
                    {driver.best_lap_number && (
                      <span className="muted"> {t('laps.lapNumber', { number: driver.best_lap_number })}</span>
                    )}
                  </td>
                  <td>
                    <AverageCell average={driver.average} />
                  </td>
                  <td>
                    <AverageCell average={driver.clean_average} />
                  </td>
                  {data.has_sectors && (
                    <td>
                      {formatLapTime(driver.theoretical_ms)}{' '}
                      {driver.theoretical_ms !== null && <span className="badge">{t('laps.theoreticalLabel')}</span>}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="muted">
        {t('laps.averageHelp')} {t('laps.cleanHelp', { rules })}{' '}
        {data.has_sectors && t('laps.theoreticalHelp')}
      </p>
    </>
  )
}

/** Lap time against lap number. Very slow laps go off the top so the race pace stays readable. */
function LapChart({ drivers }: { drivers: DriverLaps[] }) {
  const { t } = useTranslation()
  const valid = drivers.flatMap((d) => d.laps.filter((lap) => lap.valid).map((lap) => lap.time_ms))
  if (valid.length < 2) return null
  const best = Math.min(...valid)
  const top = Math.round(best * 1.12)
  const maxLap = Math.max(...drivers.flatMap((d) => d.laps.map((lap) => lap.lap_number)))
  const width = 640
  const height = 240
  const pad = { left: 56, right: 12, top: 12, bottom: 28 }
  const x = (lap: number) => pad.left + ((lap - 1) / Math.max(maxLap - 1, 1)) * (width - pad.left - pad.right)
  const y = (ms: number) => pad.top + ((Math.min(ms, top) - best) / (top - best)) * (height - pad.top - pad.bottom)
  const ticks = [best, Math.round((best + top) / 2), top]
  return (
    <figure className="lap-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t('laps.chart')}>
        {ticks.map((ms) => (
          <g key={ms}>
            <line x1={pad.left} x2={width - pad.right} y1={y(ms)} y2={y(ms)} className="grid" />
            <text x={pad.left - 6} y={y(ms) + 4} textAnchor="end" className="axis">
              {formatLapTime(ms)}
            </text>
          </g>
        ))}
        {Array.from({ length: maxLap }, (_, i) => i + 1).map((lap) => (
          <text key={lap} x={x(lap)} y={height - 8} textAnchor="middle" className="axis">
            {lap}
          </text>
        ))}
        {drivers.map((driver, index) => {
          const color = LINE_COLORS[index % LINE_COLORS.length]
          const points = driver.laps.map((lap) => `${x(lap.lap_number)},${y(lap.time_ms)}`).join(' ')
          return (
            <g key={driver.entry_id}>
              <polyline points={points} fill="none" stroke={color} strokeWidth={2} />
              {driver.laps.map((lap) => (
                <circle
                  key={lap.lap_number}
                  cx={x(lap.lap_number)}
                  cy={y(lap.time_ms)}
                  r={lap.valid ? 3 : 4}
                  fill={lap.valid ? color : 'none'}
                  stroke={color}
                >
                  <title>
                    {driver.driver_name} · {t('laps.lapNumber', { number: lap.lap_number })} ·{' '}
                    {formatLapTime(lap.time_ms)}
                    {!lap.valid && ` · ${t('laps.invalid')}`}
                  </title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
      <figcaption>
        {drivers.map((driver, index) => (
          <span key={driver.entry_id} className="legend-item">
            <span className="swatch" style={{ background: LINE_COLORS[index % LINE_COLORS.length] }} />
            {driver.driver_name}
          </span>
        ))}
        <span className="muted"> · {t('laps.chartHelp', { limit: formatLapTime(top) })}</span>
      </figcaption>
    </figure>
  )
}

function DriverTable({ driver, hasSectors }: { driver: DriverLaps; hasSectors: boolean }) {
  const { t } = useTranslation()
  const sectorCount = driver.best_sectors_ms.length
  return (
    <details className="card">
      <summary>
        #{driver.number} {driver.driver_name} · {t('laps.count', { count: driver.laps.length })}
      </summary>
      <div className="table-wrap">
        <table aria-label={t('laps.tableFor', { name: driver.driver_name })}>
          <thead>
            <tr>
              <th scope="col">{t('laps.lap')}</th>
              <th scope="col">{t('laps.time')}</th>
              {hasSectors &&
                Array.from({ length: sectorCount }, (_, i) => (
                  <th key={i} scope="col">
                    S{i + 1}
                  </th>
                ))}
              <th scope="col">{t('laps.validity')}</th>
              <th scope="col">{t('laps.pit')}</th>
              <th scope="col">{t('laps.tyre')}</th>
            </tr>
          </thead>
          <tbody>
            {driver.laps.map((lap) => (
              <tr key={lap.lap_number} className={lap.valid ? undefined : 'invalid-lap'}>
                <td>{lap.lap_number}</td>
                <td className={lap.time_mark ?? undefined}>
                  {formatLapTime(lap.time_ms)} <Mark mark={lap.time_mark} />
                </td>
                {hasSectors &&
                  Array.from({ length: sectorCount }, (_, i) => (
                    <td key={i} className={lap.sector_marks[i] ?? undefined}>
                      {formatLapTime(lap.sectors_ms[i])} <Mark mark={lap.sector_marks[i]} />
                    </td>
                  ))}
                <td>
                  {lap.valid
                    ? t('laps.valid')
                    : `✕ ${lap.cuts > 0 ? t('laps.cuts', { count: lap.cuts }) : t('laps.invalid')}`}
                </td>
                <td>{lap.pit ? t(`laps.pitStatus.${lap.pit}`) : ''}</td>
                <td>{lap.tyre}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
