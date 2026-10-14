import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import { formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { TabEmpty } from './TabEmpty'

/** Driving advice for the signed-in driver, from their own telemetry laps. */
export function EngineerSection({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const load = useLoad(
    () => api.GET('/api/rounds/{round_id}/engineer', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const data = load.data
  // The API answers "no_driver_profile" when the account has no driver.
  if (load.failed) {
    return (
      <TabEmpty
        heading={t('engineer.title')}
        icon="user"
        title={t('tabEmpty.noProfile')}
        text={t('tabEmpty.engineerProfile')}
      >
        <Link className="small-link" to="/">
          {t('tabEmpty.goHome')}
        </Link>
      </TabEmpty>
    )
  }
  if (!data) return null
  if (data.laps.length === 0) {
    return (
      <TabEmpty
        heading={t('engineer.title')}
        icon="timer"
        title={t('tabEmpty.noOwnLaps')}
        text={t('tabEmpty.engineerLaps')}
      />
    )
  }
  const reference = data.reference

  return (
    <section aria-label={t('engineer.title')}>
      <h2>{t('engineer.title')}</h2>
      {reference ? (
        <p>
          {t(reference.own ? 'engineer.referenceOwn' : 'engineer.reference', {
            driver: reference.driver_name,
            lap: reference.lap_number,
            time: formatLapTime(reference.lap_time_ms),
          })}{' '}
          {t('engineer.lapsUsed', { count: data.laps.length })}
          {data.lap_length_m && ` · ${t('engineer.length', { meters: data.lap_length_m })}`}
        </p>
      ) : (
        <p className="muted">{t('engineer.notEnough')}</p>
      )}
      <p className="muted">{t('engineer.caution')}</p>
      {reference && data.advice.length === 0 && <p>{t('engineer.noAdvice', { zones: data.zones })}</p>}
      <ul className="list">
        {data.advice.map((item) => (
          <li key={`${item.kind}-${item.zone}`} className="card">
            <strong>
              {t(`engineer.kind.${item.kind}.title`, { zone: item.zone, position: Math.round(item.position * 100) })}
            </strong>
            <p>
              {t(`engineer.kind.${item.kind}.finding`, {
                difference: item.difference,
                reference: item.reference_value,
                showing: item.laps_showing,
                total: item.laps_total,
              })}
            </p>
            <p className="muted">
              {t('engineer.evidence')}: {item.lap_values.join(' · ')} {t(`engineer.kind.${item.kind}.unit`)}
            </p>
            <p>
              {t('engineer.test')}: {t(`engineer.kind.${item.kind}.test`)}
            </p>
          </li>
        ))}
      </ul>
      <p className="muted">
        {t('engineer.setupOff', { missing: data.setup_missing.map((m) => t(`engineer.missing.${m}`)).join(', ') })}
      </p>
    </section>
  )
}
