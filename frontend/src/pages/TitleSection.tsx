import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useLoad } from '../lib/useLoad'

/** Who can still win the title. The math uses the same rules as the standings.
 * Each contender is a bar: the points now, then the most points the driver can still reach.
 * A line marks the total that makes the leader champion. */
export function TitleSection({ seasonId }: { seasonId: number }) {
  const { t } = useTranslation()
  const title = useLoad(
    () => api.GET('/api/seasons/{season_id}/title', { params: { path: { season_id: seasonId } } }),
    [seasonId],
  )
  const data = title.data
  if (!data) return null
  if (data.rounds_with_result === 0 || data.drivers.length === 0) {
    // Before the first result there is no fight yet. The box says what will be here.
    return (
      <section aria-label={t('title.title')}>
        <h2>{t('title.title')}</h2>
        <p className="muted">{t('title.empty')}</p>
      </section>
    )
  }
  const leader = data.drivers.find((d) => d.entry_id === data.leader_id)
  const contenders = data.drivers.filter((d) => d.status !== 'eliminated')
  const line = leader && data.leader_target !== null ? leader.points + data.leader_target : null
  const scale = Math.max(1, line ?? 0, ...contenders.map((d) => d.best_case))
  const pct = (points: number) => `${(points / scale) * 100}%`
  return (
    <section aria-label={t('title.title')}>
      <h2>{t('title.title')}</h2>
      {leader && (
        <p>
          <strong>
            {leader.status === 'champion'
              ? t('title.champion', { name: leader.driver_name })
              : data.leader_target !== null
                ? t('title.target', { name: leader.driver_name, points: data.leader_target, count: data.remaining_rounds })
                : t('title.dependsOnRivals', { name: leader.driver_name })}
          </strong>
        </p>
      )}
      {leader?.status !== 'champion' && (
        <>
          <ul className="title-bars">
            {contenders.map((driver) => (
              <li key={driver.entry_id}>
                <span className="title-name">
                  {driver.driver_name}
                  <span
                    className={driver.own_destiny ? 'badge title-own' : 'badge'}
                    title={driver.own_destiny ? t('title.ownDestiny') : t('title.needsHelp')}
                  >
                    {driver.own_destiny ? t('title.ownShort') : t('title.helpShort')}
                  </span>
                </span>
                <span
                  className="title-track"
                  role="img"
                  aria-label={t('title.barLabel', {
                    name: driver.driver_name,
                    points: driver.points,
                    best: driver.best_case,
                  })}
                >
                  <span className="title-max" style={{ width: pct(driver.best_case) }} />
                  <span className="title-now" style={{ width: pct(driver.points) }} />
                  {line !== null && <span className="title-line" style={{ left: pct(line) }} />}
                </span>
                <span className="title-nums" aria-hidden="true">
                  {driver.points}
                  <small> / {driver.best_case}</small>
                </span>
              </li>
            ))}
          </ul>
          <p className="title-legend muted">
            <span className="key now" aria-hidden="true" /> {t('title.now')}
            <span className="key max" aria-hidden="true" /> {t('title.max')}
            {line !== null && leader && (
              <>
                <span className="key line" aria-hidden="true" /> {t('title.line', { name: leader.driver_name, points: line })}
              </>
            )}
          </p>
        </>
      )}
      {data.drivers.some((d) => d.status === 'eliminated') && (
        <p className="muted">
          {t('title.eliminated', {
            names: data.drivers
              .filter((d) => d.status === 'eliminated')
              .map((d) => d.driver_name)
              .join(', '),
          })}
        </p>
      )}
      <details>
        <summary>{t('title.assumptions')}</summary>
        <ul>
          <li>
            {t('title.remaining', { count: data.remaining_rounds, planned: data.planned_rounds })}
          </li>
          <li>{t('title.maxPoints', { top: data.max_per_round, second: data.max_if_not_winner })}</li>
          <li>{t('title.countback')}</li>
          <li>{t('title.noPenalties')}</li>
          {data.leader_target !== null && <li>{t('title.targetHelp')}</li>}
          {data.limits.map((limit) => (
            <li key={limit} className="warning">
              {t(`title.limits.${limit}`)}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
