import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useLoad } from '../lib/useLoad'

/** Who can still win the title. The math uses the same rules as the standings. */
export function TitleSection({ seasonId }: { seasonId: number }) {
  const { t } = useTranslation()
  const title = useLoad(
    () => api.GET('/api/seasons/{season_id}/title', { params: { path: { season_id: seasonId } } }),
    [seasonId],
  )
  const data = title.data
  if (!data || data.rounds_with_result === 0 || data.drivers.length === 0) return null
  const leader = data.drivers.find((d) => d.entry_id === data.leader_id)
  const contenders = data.drivers.filter((d) => d.status !== 'eliminated')
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
        <ul className="list">
          {contenders.map((driver) => (
            <li key={driver.entry_id}>
              {driver.driver_name}: {t('title.bestCase', { points: driver.best_case })}
              {driver.own_destiny ? ` · ${t('title.ownDestiny')}` : ` · ${t('title.needsHelp')}`}
            </li>
          ))}
        </ul>
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
