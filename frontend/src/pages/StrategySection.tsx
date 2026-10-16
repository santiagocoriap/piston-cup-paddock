import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Stint = components['schemas']['StintOut']

/** The color class of a tyre. AC mods name tyres in many ways ("S", "SM", "Soft", "W").
 * The first letter decides: soft, medium, hard, intermediate, wet. Any other tyre is gray. */
function tyreTone(tyre: string): string {
  const first = tyre.trim().toLowerCase()[0]
  return { s: 'tyre-soft', m: 'tyre-medium', h: 'tyre-hard', i: 'tyre-inter', w: 'tyre-wet' }[first ?? ''] ?? 'tyre-other'
}

/** The stints and tyres of each driver in the race, as a bar from the first to the last lap.
 * The drivers come in the order of the result. */
export function StrategySection({ roundId, order }: { roundId: number; order: number[] }) {
  const { t } = useTranslation()
  const laps = useLoad(
    () => api.GET('/api/rounds/{round_id}/laps', { params: { path: { round_id: roundId }, query: { session: 'race' } } }),
    [roundId],
  )
  const drivers = laps.data?.drivers.filter((driver) => driver.stints.length > 0) ?? []
  if (drivers.length === 0) return null
  const rank = (entryId: number) => {
    const index = order.indexOf(entryId)
    return index === -1 ? order.length : index
  }
  drivers.sort((a, b) => rank(a.entry_id) - rank(b.entry_id))
  const total = Math.max(...drivers.map((driver) => driver.stints[driver.stints.length - 1].last_lap))
  const tyres = [...new Set(drivers.flatMap((driver) => driver.stints.map((stint) => stint.tyre || '?')))]

  return (
    <section className="strategy" aria-labelledby="strategy-title">
      <h2 id="strategy-title">{t('strategy.title')}</h2>
      {!laps.data?.has_pit_data && <p className="muted">{t('strategy.noPitData')}</p>}
      <ol className="strategy-rows">
        {drivers.map((driver) => (
          <li key={driver.entry_id}>
            <span className="strategy-name" title={driver.driver_name}>
              <span className="car-number">#{driver.number}</span>
              {driver.driver_name}
            </span>
            <span className="strategy-bar" role="list" aria-label={t('strategy.driver', { name: driver.driver_name })}>
              {driver.stints.map((stint) => (
                <StintBlock key={stint.number} stint={stint} total={total} />
              ))}
            </span>
            <span className="strategy-stops">{t('strategy.stops', { count: driver.stints.length - 1 })}</span>
          </li>
        ))}
      </ol>
      <p className="strategy-legend muted">
        {tyres.map((tyre) => (
          <span key={tyre}>
            <span className={`tyre-dot ${tyreTone(tyre)}`} aria-hidden="true" />
            {tyre}
          </span>
        ))}
        <span>{t('strategy.laps', { count: total })}</span>
      </p>
      <details>
        <summary>{t('strategy.table')}</summary>
        <div className="table-wrap">
          <table className="strategy-table">
            <thead>
              <tr>
                <th scope="col">{t('season.driver')}</th>
                <th scope="col">{t('strategy.stintColumn')}</th>
                <th scope="col">{t('strategy.tyre')}</th>
                <th scope="col">{t('strategy.lapsColumn')}</th>
                <th scope="col" className="r">
                  {t('strategy.bestColumn')}
                </th>
                <th scope="col" className="r">
                  {t('strategy.averageColumn')}
                </th>
              </tr>
            </thead>
            <tbody>
              {drivers.flatMap((driver) =>
                driver.stints.map((stint) => (
                  <tr key={`${driver.entry_id}-${stint.number}`}>
                    <td>{stint.number === 1 ? driver.driver_name : ''}</td>
                    <td>{stint.number}</td>
                    <td>
                      <span className={`tyre-dot ${tyreTone(stint.tyre)}`} aria-hidden="true" /> {stint.tyre || '?'}
                    </td>
                    <td>
                      {stint.first_lap === stint.last_lap ? stint.first_lap : `${stint.first_lap}–${stint.last_lap}`} (
                      {stint.laps})
                    </td>
                    <td className="r">{stint.best_ms ? formatLapTime(stint.best_ms) : '—'}</td>
                    <td className="r">{stint.average_ms ? formatLapTime(stint.average_ms) : '—'}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

function StintBlock({ stint, total }: { stint: Stint; total: number }) {
  const { t } = useTranslation()
  const left = ((stint.first_lap - 1) / total) * 100
  const width = (stint.laps / total) * 100
  const label = t('strategy.stint', {
    number: stint.number,
    tyre: stint.tyre || '?',
    first: stint.first_lap,
    last: stint.last_lap,
    count: stint.laps,
  })
  const detail = [
    label,
    stint.best_ms ? t('strategy.best', { time: formatLapTime(stint.best_ms) }) : null,
    stint.average_ms ? t('strategy.average', { time: formatLapTime(stint.average_ms) }) : null,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <span
      role="listitem"
      className={`stint ${tyreTone(stint.tyre)}`}
      style={{ left: `${left}%`, width: `${width}%` }}
      title={detail}
      aria-label={detail}
    >
      <span aria-hidden="true">{stint.tyre || '?'}</span>
    </span>
  )
}
