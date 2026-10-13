import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Combobox } from '../components/Combobox'
import { Dialog } from '../components/Dialog'
import { EventTime } from '../components/EventTime'
import { Explainer, StatusBadge } from '../components/Feedback'
import { Icon, type IconName } from '../components/Icon'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useMe } from '../session'

type Card = components['schemas']['SeasonCardOut']
type NextRound = components['schemas']['NextRoundOut']
type Ballot = components['schemas']['BallotSummary']
type Conditions = components['schemas']['ConditionsOut']
type Answer = 'yes' | 'maybe' | 'no'

/** The first thing a driver sees: the next race, what to do, the position, and the last results. */
export function DashboardSection() {
  const { t } = useTranslation()
  const me = useMe()
  const dashboard = useLoad(() => api.GET('/api/dashboard'), [])
  const [linking, setLinking] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const hideKey = `paddock.notRacing.${me.id}`
  const [notRacing, setNotRacing] = useState(() => {
    try {
      return localStorage.getItem(hideKey) === 'yes'
    } catch {
      return false
    }
  })
  const data = dashboard.data
  if (!data) return null

  function hideBox() {
    setNotRacing(true)
    try {
      localStorage.setItem(hideKey, 'yes')
    } catch {
      // Private windows can refuse storage. The box then stays hidden for this page only.
    }
  }

  const withNext = data.seasons.filter((card) => card.next_round)
  const main = [...withNext].sort(byNextDate)[0] ?? data.seasons[0]

  return (
    <section className="dashboard" aria-labelledby="home-title">
      <h1 id="home-title">{t('dashboard.hello', { name: me.username })}</h1>
      {notice && (
        <p role="status" className="notice-ok">
          <Icon name="check" small />
          {notice}
        </p>
      )}
      {!data.has_driver_profile && !notRacing && (
        <div className="empty-home">
          <span className="champ-icon">
            <Icon name="user" />
          </span>
          <div>
            <p className="empty-title">{t('dashboard.noProfileTitle')}</p>
            <p className="muted">{me.is_admin ? t('dashboard.noProfileAdmin') : t('dashboard.noProfile')}</p>
          </div>
          <div className="empty-home-actions">
            {me.is_admin && (
              <button type="button" onClick={() => setLinking(true)}>
                {t('dashboard.pickProfile')}
              </button>
            )}
            <button type="button" className="secondary" onClick={hideBox}>
              {t('dashboard.notRacing')}
            </button>
          </div>
        </div>
      )}
      {me.is_admin && (
        <Dialog open={linking} title={t('dashboard.pickProfileTitle')} onClose={() => setLinking(false)}>
          {linking && (
            <LinkMyProfile
              userId={me.id}
              onLinked={(name) => {
                setLinking(false)
                setNotice(t('dashboard.linked', { name }))
                dashboard.reload()
              }}
            />
          )}
        </Dialog>
      )}
      {data.has_driver_profile && data.seasons.length === 0 && (
        <div className="empty-home">
          <span className="champ-icon">
            <Icon name="flag" />
          </span>
          <div>
            <p className="empty-title">{t('dashboard.noSeasonsTitle')}</p>
            <p className="muted">{t('dashboard.noSeasons')}</p>
          </div>
        </div>
      )}
      {main && <SeasonHome key={main.season_id} card={main} />}
      {data.seasons.length > 1 && (
        <section aria-labelledby="other-seasons">
          <h2 id="other-seasons">{t('dashboard.otherSeasons')}</h2>
          <ul className="home-others">
            {data.seasons
              .filter((card) => card !== main)
              .map((card) => (
                <li key={card.season_id}>
                  <Link to={`/seasons/${card.season_id}`}>
                    {card.championship_name} · {card.season_name}
                  </Link>
                  <span className="muted">
                    P{card.rank} · {card.points} pts
                  </span>
                  {card.next_round && (
                    <Link to={`/rounds/${card.next_round.round_id}`}>
                      {t('round.title', { number: card.next_round.round_number })} · {card.next_round.track_name}
                    </Link>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}
    </section>
  )
}

function byNextDate(a: Card, b: Card): number {
  const da = a.next_round?.scheduled_at ?? '9999'
  const db = b.next_round?.scheduled_at ?? '9999'
  return da.localeCompare(db)
}

function SeasonHome({ card }: { card: Card }) {
  const { t } = useTranslation()
  const [attendance, setAttendance] = useState<{ mine: string | null; attending: number } | null>(null)
  const ballots = useLoad(
    () => api.GET('/api/seasons/{season_id}/ballots', { params: { path: { season_id: card.season_id } } }),
    [card.season_id],
  )
  const next = card.next_round
  const mine = attendance?.mine ?? next?.my_attendance ?? null
  const attending = attendance?.attending ?? next?.attending ?? 0
  const openBallots = (ballots.data ?? []).filter((ballot) => ballot.status === 'open')

  return (
    <article aria-label={`${card.championship_name} · ${card.season_name}`}>
      {next ? (
        <NextRace
          card={card}
          next={next}
          mine={mine}
          attending={attending}
          onAnswered={(answer, count) => setAttendance({ mine: answer, attending: count })}
        />
      ) : (
        <p className="muted">{t('dashboard.noNext')}</p>
      )}
      <div className="home-grid">
        <div>
          <ToDo card={card} openBallots={openBallots} />
          <Recent card={card} />
        </div>
        <div className="home-side">
          <Standing card={card} />
          {next && <Handicap next={next} />}
        </div>
      </div>
    </article>
  )
}

function NextRace({
  card,
  next,
  mine,
  attending,
  onAnswered,
}: {
  card: Card
  next: NextRound
  mine: string | null
  attending: number
  onAnswered: (answer: Answer, attending: number) => void
}) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [changing, setChanging] = useState(false)

  async function answer(value: Answer) {
    setError(null)
    const { data, error: failure } = await api.PUT('/api/rounds/{round_id}/attendance', {
      params: { path: { round_id: next.round_id } },
      body: { answer: value },
    })
    if (data) {
      onAnswered(value, data.yes)
      setChanging(false)
    } else setError(errorMessage(t, failure))
  }

  const answered = mine && !changing
  return (
    <section className="hero" aria-labelledby="next-race">
      <div className="hero-main">
        <p className="eyebrow">
          <span className="badge status-badge new">
            <Icon name="flag" small />
            {t('dashboard.next')}
          </span>
          <span>
            {t('round.title', { number: next.round_number })} · {card.championship_name} · {card.season_name}
          </span>
        </p>
        <h2 id="next-race" className="hero-title">
          {next.track_name}
        </h2>
        <p className="hero-when">
          <span className="hero-layout">{next.layout_name}</span>
          <span>
            <EventTime iso={next.scheduled_at} eventTimeZone={next.event_timezone} />
          </span>
        </p>
        {next.scheduled_at && <Countdown iso={next.scheduled_at} roundId={next.round_id} />}
        {answered ? (
          <div className="hero-answer" role="status">
            <StatusBadge status={mine === 'yes' ? 'confirmed' : mine === 'maybe' ? 'pending' : 'unknown'}>
              {t('dashboard.myAttendance', { answer: t(`attendance.answers.${mine}`) })}
            </StatusBadge>
            <button type="button" className="secondary small" onClick={() => setChanging(true)}>
              {t('dashboard.changeAnswer')}
            </button>
          </div>
        ) : (
          <div>
            <p className="hero-question">{t('dashboard.question')}</p>
            <div className="hero-attend" role="group" aria-label={t('dashboard.question')}>
              <button type="button" onClick={() => answer('yes')}>
                <Icon name="check" />
                {t('dashboard.yes')}
              </button>
              <button type="button" className="secondary" onClick={() => answer('maybe')}>
                {t('attendance.answers.maybe')}
              </button>
              <button type="button" className="secondary" onClick={() => answer('no')}>
                {t('dashboard.no')}
              </button>
            </div>
          </div>
        )}
        <p className="muted hero-count">{t('dashboard.attending', { count: attending })}</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Link className="button-link secondary-link" to={`/rounds/${next.round_id}`}>
          {t('dashboard.briefing')}
        </Link>
      </div>
      <dl className="hero-facts">
        {next.track_outline_url && (
          <img
            className="hero-outline"
            src={next.track_outline_url}
            alt={t('dashboard.outlineAlt', { track: next.track_name, layout: next.layout_name })}
          />
        )}
        {next.car_image_url && <img className="hero-car" src={next.car_image_url} alt={card.car_name} />}
        <div>
          <dt>{t('dashboard.carLabel')}</dt>
          <dd>{t('dashboard.car', { number: card.entry_number, car: card.car_name })}</dd>
        </div>
        <div>
          <dt>{t('dashboard.handicap')}</dt>
          <dd>
            {next.ballast_kg} kg · {next.restrictor_pct} %
          </dd>
        </div>
        <ConditionFacts conditions={next.conditions} />
      </dl>
    </section>
  )
}

function Countdown({ iso, roundId }: { iso: string; roundId: number }) {
  const { t } = useTranslation()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  const left = new Date(iso).getTime() - now
  if (left <= 0)
    return (
      <p className="hero-live">
        <span className="live-dot" aria-hidden="true" />
        <b>{t('dashboard.live')}</b>
        <Link to={`/rounds/${roundId}`}>{t('dashboard.liveLink')}</Link>
      </p>
    )
  const minutes = Math.floor(left / 60_000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  const label = t('dashboard.countdown', { days, hours, minutes: mins })
  return (
    <div className="countdown" role="timer" aria-label={label}>
      <div>
        <FlipValue value={String(days)} />
        <span>{t('dashboard.days', { count: days })}</span>
      </div>
      <div>
        <FlipValue value={String(hours)} />
        <span>{t('dashboard.hours', { count: hours })}</span>
      </div>
      <div>
        <FlipValue value={String(mins).padStart(2, '0')} />
        <span>{t('dashboard.minutes')}</span>
      </div>
    </div>
  )
}

function ToDo({ card, openBallots }: { card: Card; openBallots: Ballot[] }) {
  const { t, i18n } = useTranslation()
  const items: {
    key: string
    urgent: boolean
    done?: boolean
    icon: IconName
    title: string
    detail: string
    to: string
    action: string
  }[] = []
  for (const ballot of openBallots) {
    const voted = ballot.voted === true
    const closes = ballot.closes_at ? formatDateTime(ballot.closes_at, i18n.language) : null
    let title = t('dashboard.todo.vote', { title: ballot.title })
    if (ballot.parent_id) title = t('dashboard.todo.runoff', { title: ballot.title })
    if (voted) title = t('dashboard.todo.voted', { title: ballot.title })
    items.push({
      key: 'ballot-' + ballot.id,
      urgent: false,
      done: voted,
      icon: voted ? 'check' : 'flag',
      title,
      detail: closes ? t('dashboard.todo.closes', { date: closes }) : t('dashboard.todo.voteDetail'),
      to: '/ballots/' + ballot.id,
      action: voted ? t('dashboard.todo.change') : t('dashboard.todo.voteAction'),
    })
  }
  for (const report of card.new_reports)
    items.push({
      key: `report-${report.round_id}`,
      urgent: false,
      icon: 'info',
      title: t('dashboard.todo.report', { round: report.round_number, track: report.track_name }),
      detail: t('dashboard.newReports'),
      to: `/rounds/${report.round_id}`,
      action: t('dashboard.todo.read'),
    })

  // Open work first, done work last.
  items.sort((a, b) => Number(Boolean(a.done)) - Number(Boolean(b.done)))

  return (
    <section aria-labelledby="todo">
      <h2 id="todo">{t('dashboard.todo.title')}</h2>
      {items.length === 0 ? (
        <p className="muted">{t('dashboard.todo.none')}</p>
      ) : (
        <ol className="todo">
          {items.map((item) => (
            <li key={item.key}>
              <span className={item.urgent ? 'prio urgent' : item.done ? 'prio done' : 'prio'}>
                <Icon name={item.icon} />
              </span>
              <div>
                <b>{item.title}</b>
                <span className="muted">{item.detail}</span>
              </div>
              <Link className="small-link" to={item.to}>
                {item.action}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

type Result = Card['history'][number]

/** "win", "podium", "out" (DNF, DNS, or DSQ), or "" for any other finish. */
function resultTone(result: Result): string {
  if (result.status !== 'finished') return 'out'
  if (result.position === 1) return 'win'
  if (result.position !== null && result.position <= 3) return 'podium'
  return ''
}

function Recent({ card }: { card: Card }) {
  const { t } = useTranslation()
  const newest = [...card.history].reverse().slice(0, 5)
  return (
    <section aria-labelledby="recent">
      <h2 id="recent">{t('dashboard.recent')}</h2>
      {newest.length === 0 ? (
        <p className="muted">{t('dashboard.noRecent')}</p>
      ) : (
        <>
          <Trend history={card.history} entries={card.entries} />
          <ol className="result-chips">
            {newest.map((result) => (
              <li key={result.round_id} className={`result-chip ${resultTone(result)}`.trim()}>
                <Link to={`/rounds/${result.round_id}`}>
                  <span className="result-round">
                    {t('round.title', { number: result.round_number })} · {result.track_name}
                  </span>
                  <span className="result-place num">
                    {result.position ? `P${result.position}` : result.status.toUpperCase()}
                    {result.status !== 'finished' && result.position ? ` ${result.status.toUpperCase()}` : ''}
                  </span>
                  <span className="result-points num">{t('dashboard.points', { count: result.points })}</span>
                </Link>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  )
}

/** The position in each round as a small line. P1 is at the top. */
function Trend({ history, entries }: { history: Result[]; entries: number }) {
  const { t } = useTranslation()
  const placed = history.filter((r) => r.position !== null)
  if (placed.length < 2) return null
  const width = 400
  const height = 72
  const pad = 8
  const left = 34
  const worst = Math.max(2, entries, ...placed.map((r) => r.position ?? 1))
  const x = (index: number) => left + (index * (width - left - pad)) / (placed.length - 1)
  const y = (position: number) => pad + ((position - 1) * (height - 2 * pad)) / (worst - 1)
  const points = placed.map((r, index) => `${x(index)},${y(r.position ?? worst)}`).join(' ')
  const label = `${t('dashboard.trend')}: ${placed
    .map((r) => `${t('round.title', { number: r.round_number })} P${r.position}`)
    .join(', ')}`
  return (
    <svg className="trend" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <text className="trend-scale" x={0} y={y(1) + 4} aria-hidden="true">
        {t('dashboard.trendScale', { position: 1 })}
      </text>
      <text className="trend-scale" x={0} y={y(worst) + 4} aria-hidden="true">
        {t('dashboard.trendScale', { position: worst })}
      </text>
      <line className="trend-top" x1={left} x2={width - pad} y1={y(1)} y2={y(1)} />
      <polyline points={points} />
      {placed.map((r, index) => (
        <circle
          key={r.round_id}
          className={index === placed.length - 1 ? 'last' : undefined}
          cx={x(index)}
          cy={y(r.position ?? worst)}
          r={index === placed.length - 1 ? 4.5 : 3}
        >
          <title>{`${t('round.title', { number: r.round_number })} · P${r.position}`}</title>
        </circle>
      ))}
    </svg>
  )
}

function Standing({ card }: { card: Card }) {
  const { t } = useTranslation()
  const gap = card.leader_points - card.points
  return (
    <section className="card" aria-labelledby="standing">
      <h3 id="standing">{t('dashboard.position')}</h3>
      <p className="stat-value">
        P{card.rank} <small className="muted">{t('dashboard.of', { count: card.entries })}</small>
      </p>
      <p className="muted">
        {card.points} pts · {gap > 0 ? t('dashboard.gap', { count: gap }) : t('dashboard.leader')} ·{' '}
        {t('dashboard.winsCount', { count: card.wins })}
      </p>
      {card.nearby.length > 1 && (
        <table className="nearby">
          <caption className="sr-only">{t('dashboard.nearby')}</caption>
          <tbody>
            {card.nearby.map((row) => {
              const diff = row.points - card.points
              return (
                <tr key={row.rank} className={row.me ? 'me-row' : undefined}>
                  <td className="num">P{row.rank}</td>
                  <td>{row.me ? t('dashboard.you') : row.name}</td>
                  <td className="num">{row.points}</td>
                  <td className="num nearby-gap">{row.me ? '' : diff > 0 ? `+${diff}` : `−${Math.abs(diff)}`}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <Link className="small-link" to={`/seasons/${card.season_id}`}>
        {t('dashboard.standings')}
      </Link>
    </section>
  )
}

/** A value that flips like a timing board when it changes. */
function FlipValue({ value }: { value: string }) {
  // A new key starts the animation again for each new value.
  return (
    <b className="flip" key={value}>
      {value}
    </b>
  )
}

function Handicap({ next }: { next: NextRound }) {
  const { t } = useTranslation()
  return (
    <section className="card" aria-labelledby="handicap">
      <h3 id="handicap">{t('dashboard.handicapFor', { track: next.track_name })}</h3>
      <Scale
        label={t('dashboard.ballast')}
        value={next.ballast_kg}
        previous={next.previous_ballast_kg}
        max={next.ballast_cap}
        unit="kg"
      />
      <Scale
        label={t('dashboard.restrictor')}
        value={next.restrictor_pct}
        previous={next.previous_restrictor_pct}
        max={next.restrictor_cap}
        unit="%"
      />
      <div>
        <Explainer title={t('dashboard.ballast')}>{t('dashboard.ballastHelp')}</Explainer>{' '}
        <Explainer title={t('dashboard.restrictor')} label={t('dashboard.restrictor')}>
          {t('dashboard.restrictorHelp')}
        </Explainer>
      </div>
    </section>
  )
}

function Scale({
  label,
  value,
  previous,
  max,
  unit,
}: {
  label: string
  value: number
  previous: number | null
  max: number
  unit: string
}) {
  const { t } = useTranslation()
  const change = previous === null ? 0 : value - previous
  const sign = change > 0 ? '+' : '−'
  return (
    <div className="scale">
      <p className="scale-head">
        <span className="muted">{label}</span>
        <b>
          {value} {unit}
        </b>
      </p>
      {previous !== null && (
        <p className="scale-change muted">
          {change === 0
            ? t('dashboard.noChange', { previous, unit })
            : t('dashboard.changed', { previous, unit, change: sign + Math.abs(change) })}
        </p>
      )}
      <div className="scale-track" role="img" aria-label={t('dashboard.ofMax', { value, max, unit })}>
        <span className="scale-fill" style={{ width: Math.min(100, (value / max) * 100) + '%' }} />
        {previous !== null && previous !== value && (
          <span className="scale-prev" style={{ left: Math.min(100, (previous / max) * 100) + '%' }} />
        )}
      </div>
      <p className="scale-cap muted">
        <span>0</span>
        <span>{t('dashboard.max', { max, unit })}</span>
      </p>
    </div>
  )
}

function weatherIcon(weather: string): IconName {
  const text = weather.toLowerCase()
  if (/lluv|rain|torment|storm|drizzle|llovizna/.test(text)) return 'rain'
  if (/niebla|fog|bruma|mist/.test(text)) return 'fog'
  if (/nubl|cloud|cubierto|overcast/.test(text)) return 'cloud'
  if (/despej|clear|soleado|sunny/.test(text)) return 'sun'
  return 'thermometer'
}

function ConditionFacts({ conditions }: { conditions: Conditions | null }) {
  const { t } = useTranslation()
  if (!conditions)
    return (
      <div>
        <dt>{t('briefing.conditions')}</dt>
        <dd className="muted">{t('dashboard.noConditions')}</dd>
      </div>
    )
  const temps: string[] = []
  if (conditions.air_temp_c != null) temps.push(t('dashboard.air', { value: conditions.air_temp_c }))
  if (conditions.track_temp_c != null) temps.push(t('dashboard.track', { value: conditions.track_temp_c }))
  return (
    <>
      {(conditions.weather || temps.length > 0) && (
        <div>
          <dt>{t('briefing.weather')}</dt>
          <dd className="weather">
            <Icon name={weatherIcon(conditions.weather ?? '')} />
            <span>
              {conditions.weather || t('dashboard.noWeather')}
              {temps.length > 0 && <span className="muted"> · {temps.join(' · ')}</span>}
            </span>
          </dd>
        </div>
      )}
      {conditions.time_of_day && (
        <div>
          <dt>{t('briefing.timeOfDay')}</dt>
          <dd>{conditions.time_of_day}</dd>
        </div>
      )}
      {conditions.grip && (
        <div>
          <dt>{t('briefing.grip')}</dt>
          <dd>{conditions.grip}</dd>
        </div>
      )}
    </>
  )
}

/** An admin links their own account to a driver profile that has no account yet. */
function LinkMyProfile({ userId, onLinked }: { userId: number; onLinked: (name: string) => void }) {
  const { t } = useTranslation()
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const free = (drivers.data ?? []).filter((driver) => driver.user_id === null)
  return (
    <form
      className="modal-body"
      aria-label={t('dashboard.pickProfileTitle')}
      onSubmit={async (event) => {
        event.preventDefault()
        const driver = free.find((d) => String(d.id) === value)
        if (!driver) return
        setBusy(true)
        setError(null)
        const { error: apiError } = await api.POST('/api/drivers/{driver_id}/link', {
          params: { path: { driver_id: driver.id } },
          body: { user_id: userId },
        })
        setBusy(false)
        if (apiError) return setError(errorMessage(t, apiError))
        onLinked(driver.display_name)
      }}
    >
      <h3>{t('dashboard.pickProfileTitle')}</h3>
      {drivers.data && free.length === 0 ? (
        <p className="muted">{t('dashboard.noFreeProfiles')}</p>
      ) : (
        <Combobox
          label={t('dashboard.profileLabel')}
          options={free.map((d) => ({ value: String(d.id), label: d.display_name, hint: d.steam_guid ?? undefined }))}
          value={value}
          onChange={setValue}
          emptyText={t('dashboard.noProfileMatch')}
        />
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="modal-actions">
        <button type="submit" disabled={busy || !value}>
          {t('common.save')}
        </button>
      </div>
    </form>
  )
}
