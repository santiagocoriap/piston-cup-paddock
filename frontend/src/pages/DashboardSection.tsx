import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { EventTime } from '../components/EventTime'
import { useLoad } from '../lib/useLoad'

type Card = components['schemas']['SeasonCardOut']

/** The first thing a driver sees: position, points, last results, and the next round. */
export function DashboardSection() {
  const { t } = useTranslation()
  const dashboard = useLoad(() => api.GET('/api/dashboard'), [])
  const data = dashboard.data
  if (!data) return null

  return (
    <section className="dashboard">
      <h1>{t('dashboard.title')}</h1>
      {!data.has_driver_profile && <p className="muted">{t('dashboard.noProfile')}</p>}
      {data.has_driver_profile && data.seasons.length === 0 && <p className="muted">{t('dashboard.noSeasons')}</p>}
      <div className="dashboard-cards">
        {data.seasons.map((card) => (
          <SeasonCard key={card.season_id} card={card} />
        ))}
      </div>
    </section>
  )
}

function SeasonCard({ card }: { card: Card }) {
  const { t } = useTranslation()
  const gap = card.leader_points - card.points
  const next = card.next_round
  return (
    <article className="card season-card" aria-label={`${card.championship_name} · ${card.season_name}`}>
      <header>
        <p className="muted">
          {card.championship_name} · <Link to={`/seasons/${card.season_id}`}>{card.season_name}</Link>
        </p>
        <p className="muted">{t('dashboard.car', { number: card.entry_number, car: card.car_name })}</p>
      </header>

      <div className="stats">
        <div>
          <span className="stat-label">{t('dashboard.position')}</span>
          <span className="stat-value">P{card.rank}</span>
          <span className="muted">{t('dashboard.of', { count: card.entries })}</span>
        </div>
        <div>
          <span className="stat-label">{t('dashboard.points')}</span>
          <span className="stat-value">{card.points}</span>
          <span className="muted">{gap > 0 ? t('dashboard.gap', { count: gap }) : t('dashboard.leader')}</span>
        </div>
        <div>
          <span className="stat-label">{t('dashboard.wins')}</span>
          <span className="stat-value">{card.wins}</span>
        </div>
      </div>

      {card.new_reports.length > 0 && (
        <>
          <h3>{t('dashboard.newReports')}</h3>
          <ul className="recent">
            {card.new_reports.map((report) => (
              <li key={report.round_id}>
                <Link to={`/rounds/${report.round_id}`}>
                  R{report.round_number} · {report.track_name}
                </Link>
                <span className="badge">{t('report.new')}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>{t('dashboard.recent')}</h3>
      {card.recent.length === 0 ? (
        <p className="muted">{t('dashboard.noRecent')}</p>
      ) : (
        <ol className="recent">
          {card.recent.map((result) => (
            <li key={result.round_id}>
              <Link to={`/rounds/${result.round_id}`}>
                R{result.round_number} · {result.track_name}
              </Link>
              <span>
                {result.position ? `P${result.position}` : result.status.toUpperCase()}
                {result.status === 'dnf' && result.position ? ' DNF' : ''} · {result.points} pts
              </span>
            </li>
          ))}
        </ol>
      )}

      <h3>{t('dashboard.next')}</h3>
      {next ? (
        <div className="next-round">
          <p>
            <strong>
              R{next.round_number} · {next.track_name} · {next.layout_name}
            </strong>
          </p>
          <p className="muted">
            <EventTime iso={next.scheduled_at} eventTimeZone={next.event_timezone} />
          </p>
          <p>
            {t('dashboard.handicap')}:{' '}
            <strong>
              {next.ballast_kg} kg · {next.restrictor_pct} %
            </strong>
          </p>
          <p>
            {next.my_attendance
              ? t('dashboard.myAttendance', { answer: t(`attendance.answers.${next.my_attendance}`) })
              : t('dashboard.noAttendance')}{' '}
            · {t('dashboard.attending', { count: next.attending })}
          </p>
          <Link className="button-link" to={`/rounds/${next.round_id}`}>
            {t('dashboard.briefing')}
          </Link>
        </div>
      ) : (
        <p className="muted">{t('dashboard.noNext')}</p>
      )}
    </article>
  )
}
