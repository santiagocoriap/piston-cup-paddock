import { useTranslation } from 'react-i18next'
import type { components } from '../api/schema'
import { EventTime } from '../components/EventTime'
import { MyCarPanel, TrackPanel, WeatherPanel } from './CatalogViews'
import { DrawHistory } from './ConditionsDraw'

type RoundDetail = components['schemas']['RoundDetail']

const CONDITION_FIELDS = [
  ['time_of_day', 'timeOfDay', ''],
  ['weather', 'weather', ''],
  ['air_temp_c', 'airTemp', ' °C'],
  ['track_temp_c', 'trackTemp', ' °C'],
  ['grip', 'grip', ''],
  ['notes', 'notes', ''],
] as const

/** What a driver needs before the race: schedule, conditions, rules, and the own car. */
export function Briefing({ round }: { round: RoundDetail }) {
  const { t } = useTranslation()
  const { announced_conditions: conditions, protest_window_minutes, my_handicap: mine } = round.briefing
  const shown = CONDITION_FIELDS.filter(([key]) => {
    const value = (conditions as Record<string, unknown>)[key]
    return value !== undefined && value !== null && value !== ''
  })

  return (
    <section className="briefing" aria-label={t('briefing.title')}>
      <h2>{t('briefing.title')}</h2>
      <div className="briefing-grid">
        <div className="card">
          <h3>{t('briefing.schedule')}</h3>
          <p>
            <strong>
              {round.track_name} · {round.layout_name}
            </strong>
          </p>
          <p>
            <EventTime iso={round.scheduled_at} eventTimeZone={round.event_timezone} />
          </p>
        </div>

        <div className="card">
          <h3>{t('briefing.conditions')}</h3>
          {shown.length === 0 ? (
            <p className="muted">{t('briefing.noConditions')}</p>
          ) : (
            <dl className="lap-details">
              {shown.map(([key, label, unit]) => (
                <div key={key} className="contents">
                  <dt>{t(`briefing.${label}`)}</dt>
                  <dd>
                    {String((conditions as Record<string, unknown>)[key])}
                    {unit}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <DrawHistory roundId={round.id} />
        </div>

        {round.briefing.server_conditions && <ServerConditions round={round} />}

        {(round.briefing.restart_guidance || round.briefing.first_lap_cutoff) && (
          <div className="card">
            <h3>{t('briefing.restartGuidance')}</h3>
            {round.briefing.first_lap_cutoff && (
              <p>
                <strong>{t('briefing.cutoff')}:</strong> {round.briefing.first_lap_cutoff}
              </p>
            )}
            {round.briefing.restart_guidance && <p>{round.briefing.restart_guidance}</p>}
          </div>
        )}

        <div className="card">
          <h3>{t('briefing.myHandicap')}</h3>
          {mine ? (
            <>
              <p>
                <strong>
                  #{mine.entry_number} · {mine.car_name}
                </strong>
              </p>
              <p className="big">
                {mine.ballast_kg} kg · {mine.restrictor_pct} %
              </p>
              <p className="muted">{t(`briefing.${mine.source}`)}</p>
            </>
          ) : (
            <p className="muted">{t('briefing.notEntered')}</p>
          )}
        </div>

        <TrackPanel layoutId={round.track_layout_id} trackName={round.track_name} />
        {mine && mine.car_id !== null && mine.car_id !== undefined && <MyCarPanel carId={mine.car_id} />}
        <WeatherPanel announced={String((conditions as Record<string, unknown>).weather ?? '')} />

        <div className="card">
          <h3>{t('briefing.rules')}</h3>
          <p>{t('briefing.points', { points: round.rules.points_by_position.join('-') })}</p>
          <p className="muted">{t('briefing.protestWindow', { count: protest_window_minutes })}</p>
        </div>
      </div>
    </section>
  )
}

/** A weather name of AC, such as "3_clear" or "sol_05_broken_clouds", in words. */
function weatherName(t: (key: string, options?: Record<string, unknown>) => string, id: string | null | undefined) {
  if (!id) return null
  const key = id.replace(/^(sol_)?\d+_/, '')
  return t(`briefing.weathers.${key}`, { defaultValue: key.replaceAll('_', ' ') })
}

/** What the server used, from the collector, next to the announced conditions. */
function ServerConditions({ round }: { round: RoundDetail }) {
  const { t } = useTranslation()
  const real = round.briefing.server_conditions!
  const differ = round.briefing.conditions_differ ?? []
  const rows: [string, string | null, string][] = [
    ['weather', weatherName(t, real.weather), ''],
    ['air_temp', real.air_temp_c != null ? `${real.air_temp_c} °C` : null, 'airTemp'],
    ['track_temp', real.track_temp_c != null ? `${real.track_temp_c} °C` : null, 'trackTemp'],
    ['time_of_day', real.time_of_day ?? null, 'timeOfDay'],
    ['grip', real.grip_pct != null ? `${real.grip_pct} %` : null, 'grip'],
  ]
  return (
    <div className="card">
      <h3>{t('briefing.serverConditions')}</h3>
      <p className="muted">{t('briefing.serverFrom', { session: t(`imports.session.${real.session_type}`) })}</p>
      <dl className="lap-details">
        {rows
          .filter(([, value]) => value !== null)
          .map(([key, value, label]) => (
            <div key={key} className={differ.includes(key) ? 'contents differ' : 'contents'}>
              <dt>{t(`briefing.${label || 'weather'}`)}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
      {differ.length > 0 && (
        <p className="warning" role="status">
          {t('briefing.differ', { list: differ.map((key) => t(`briefing.differNames.${key}`)).join(', ') })}
        </p>
      )}
    </div>
  )
}

