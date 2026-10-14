import { useTranslation } from 'react-i18next'
import type { components } from '../api/schema'
import { EventTime } from '../components/EventTime'
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

        <div className="card">
          <h3>{t('briefing.rules')}</h3>
          <p>{t('briefing.points', { points: round.rules.points_by_position.join('-') })}</p>
          <p className="muted">{t('briefing.protestWindow', { count: protest_window_minutes })}</p>
        </div>
      </div>
    </section>
  )
}
