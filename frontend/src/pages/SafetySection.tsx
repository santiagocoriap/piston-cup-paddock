import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Explainer } from '../components/Feedback'
import { useLoad } from '../lib/useLoad'

/** Safety ratings, rules safety-1. Each change shows the incidents that caused it. */
export function SafetySection({ seasonId }: { seasonId: number }) {
  const { t } = useTranslation()
  const load = useLoad(
    () => api.GET('/api/seasons/{season_id}/safety', { params: { path: { season_id: seasonId } } }),
    [seasonId],
  )
  const data = load.data
  if (!data || data.drivers.length === 0) return null
  const sign = (value: number) => (value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2))

  return (
    <section aria-label={t('safety.title')}>
      <div className="section-head">
        <h2>{t('safety.title')}</h2>
        <Explainer title={t('safety.title')} label={t('safety.howItWorks')}>
          {t('safety.rules', { version: data.rules_version, laps: data.provisional_laps })}
        </Explainer>
      </div>
      <div className="table-wrap">
        <table aria-label={t('safety.title')}>
          <thead>
            <tr>
              <th scope="col">{t('season.driver')}</th>
              <th scope="col">{t('safety.rating')}</th>
              <th scope="col">{t('safety.laps')}</th>
              <th scope="col">{t('safety.points')}</th>
              <th scope="col">{t('safety.per100')}</th>
            </tr>
          </thead>
          <tbody>
            {data.drivers.map((driver) => (
              <tr key={driver.entry_id}>
                <td>{driver.driver_name}</td>
                <td className="safety-cell">
                  <b className={`safety-rating ${driver.status}`}>
                    {driver.status === 'unknown' ? '—' : driver.rating.toFixed(2)}
                  </b>
                  <span className={`badge safety-${driver.status}`}>{t(`safety.status.${driver.status}`)}</span>
                </td>
                <td>{driver.laps}</td>
                <td>{driver.points}</td>
                <td>{driver.per_100_laps ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.drivers
        .filter((driver) => driver.history.length > 0)
        .map((driver) => (
          <details key={driver.entry_id}>
            <summary>{t('safety.history', { name: driver.driver_name })}</summary>
            <ul className="list">
              {driver.history.map((change) => (
                <li key={change.round_id}>
                  <strong>{change.label}</strong>:{' '}
                  {change.status === 'unknown'
                    ? t('safety.unknownRound')
                    : t('safety.change', {
                        laps: change.laps,
                        up: sign(change.laps * 0.01),
                        points: change.points,
                        down: sign(-change.points * 0.05),
                        total: sign(change.change),
                        after: change.rating_after.toFixed(2),
                      })}
                  {change.explanation.length > 0 && (
                    <ul>
                      {change.explanation.map((text, index) => (
                        <li key={index} className="muted">
                          {text}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </details>
        ))}
    </section>
  )
}
