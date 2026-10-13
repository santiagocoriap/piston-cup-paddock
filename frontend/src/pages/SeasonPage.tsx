import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import { ActionForm } from '../components/ActionForm'
import { Icon } from '../components/Icon'
import { Loading } from '../components/Layout'
import { currentTimeZone, formatDateTime, localInputToIso } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useAdminView } from '../session'
import { BallotsSection } from './BallotsSection'
import { CalendarAdmin } from './CalendarAdmin'
import { ReportSection } from './ReportSection'
import { CloneSeasonForm, RoundTools } from './RoundTools'
import { RulesSection } from './RulesSection'
import { SafetySection } from './SafetySection'
import { TitleSection } from './TitleSection'
import { HandicapsSection } from './HandicapsSection'
import { ConditionsPoolForm } from './ConditionsDraw'

export function SeasonPage() {
  const { t, i18n } = useTranslation()
  const seasonId = Number(useParams().seasonId)
  const path = { season_id: seasonId }
  const season = useLoad(() => api.GET('/api/seasons/{season_id}', { params: { path } }), [seasonId])
  const standings = useLoad(
    () => api.GET('/api/seasons/{season_id}/standings', { params: { path } }),
    [seasonId],
  )

  const data = season.data
  const adminView = useAdminView(data?.can_manage ?? false)
  if (!data) return <Loading failed={season.failed} />
  const now = Date.now()
  const upcoming = data.rounds.filter(
    (round) => !round.cancelled && round.scheduled_at && new Date(round.scheduled_at).getTime() > now,
  )
  const next = upcoming[0]
  const played = data.rounds.filter(
    (round) => !round.cancelled && round.scheduled_at && new Date(round.scheduled_at).getTime() <= now,
  ).length
  const leader = standings.data?.[0]
  const sections: [string, string][] = [
    ['standings', t('standings.title')],
    ['title', t('seasonNav.title')],
    ['safety', t('seasonNav.safety')],
    ['handicaps', t('seasonNav.handicaps')],
    ['calendar', t('season.calendar')],
    ['ballots', t('seasonNav.ballots')],
    ['rules', t('seasonNav.rules')],
    ['report', t('seasonNav.report')],
    ['entries', t('season.entries')],
  ]

  return (
    <section className="season-page">
      <header className="season-hero">
        <div>
          <p className="eyebrow">
            <Link to={`/championships/${data.championship_id}`}>{data.championship_name}</Link>
          </p>
          <h1 className="season-title">{data.name}</h1>
          <p className="season-actions">
            <a className="small-link" href={`/api/seasons/${seasonId}/calendar.ics`} download>
              {t('calendar.download')}
            </a>
            {(['results', 'standings', 'restarts'] as const).map((kind) => (
              <a key={kind} className="small-link" href={`/api/seasons/${seasonId}/export/${kind}.csv`} download>
                {t('exports.title')}: {t(`exports.${kind}`)}
              </a>
            ))}
          </p>
        </div>
        <dl className="season-stats">
          <div>
            <dt>{t('seasonStats.rounds')}</dt>
            <dd>
              {played}
              <small>/ {data.planned_round_count}</small>
            </dd>
          </div>
          <div>
            <dt>{t('seasonStats.drivers')}</dt>
            <dd>{data.entries.length}</dd>
          </div>
          <div>
            <dt>{t('seasonStats.leader')}</dt>
            <dd className="season-stat-text">
              {leader ? (
                <>
                  {leader.driver_name}
                  <small>{leader.points} pts</small>
                </>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>{t('seasonStats.next')}</dt>
            <dd className="season-stat-text">
              {next ? (
                <Link to={`/rounds/${next.id}`}>
                  R{next.number} · {next.track_name}
                  <small>{formatDateTime(next.scheduled_at, i18n.language)}</small>
                </Link>
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
      </header>

      <div className="season-layout">
        <nav className="season-nav" aria-label={t('seasonNav.label')}>
          {sections.map(([id, label]) => (
            <a key={id} href={`#${id}`}>
              {label}
            </a>
          ))}
        </nav>

        <div className="season-body">
          <section id="standings" className="season-block">
            <h2>{t('standings.title')}</h2>
            {standings.data && standings.data.length === 0 && <p>{t('standings.noEntries')}</p>}
            {standings.data && standings.data.length > 0 && (
              <div className="table-wrap">
                <table className="standings">
                  <thead>
                    <tr>
                      <th scope="col">{t('standings.rank')}</th>
                      <th scope="col">{t('season.driver')}</th>
                      <th scope="col" className="hide-sm">
                        {t('season.car')}
                      </th>
                      {data.rounds.map((round) => (
                        <th
                          scope="col"
                          key={round.id}
                          className="round-col hide-sm"
                          title={`${round.track_name} · ${round.layout_name}`}
                        >
                          R{round.number}
                        </th>
                      ))}
                      <th scope="col" className="r">
                        {t('standings.wins')}
                      </th>
                      <th scope="col" className="points-col">
                        {t('standings.points')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {standings.data.map((row, index) => {
                      const shared = standings.data!.some((other, i) => i !== index && other.rank === row.rank)
                      const top = standings.data![0].points || 1
                      return (
                        <tr key={row.entry_id} className={row.rank === 1 ? 'leader' : undefined}>
                          <td className="pos" title={shared ? t('standings.shared') : undefined}>
                            {row.rank}
                            {shared && '='}
                          </td>
                          <td>
                            <span className="car-number">#{row.number}</span>
                            <Link to={`/drivers/${row.driver_id}`}>{row.driver_name}</Link>
                          </td>
                          <td className="muted hide-sm">{row.car_name}</td>
                          {row.rounds.map((score) => (
                            <td
                              key={score.round_number}
                              className={`round-col hide-sm ${score.position === 1 ? 'win' : ''} ${
                                score.status !== null && !score.official ? 'provisional' : ''
                              }`}
                            >
                              {score.status === null
                                ? '·'
                                : (score.position ?? t(`round.short.${score.status}`))}
                            </td>
                          ))}
                          <td className="r">{row.wins}</td>
                          <td className="points-col">
                            <span className="points-bar" aria-hidden="true">
                              <span style={{ width: `${(row.points / top) * 100}%` }} />
                            </span>
                            <span className="points">{row.points}</span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {standings.data?.some((row) => row.rounds.some((r) => r.status !== null && !r.official)) && (
              <p className="muted note">{t('season.provisionalNote')}</p>
            )}
          </section>

          <div className="season-pair">
            <section id="title" className="season-block">
              <TitleSection seasonId={seasonId} />
            </section>
            <section id="safety" className="season-block">
              <SafetySection seasonId={seasonId} />
            </section>
          </div>

          <section id="handicaps" className="season-block">
            <HandicapsSection seasonId={seasonId} rounds={data.rounds} adminView={adminView} />
          </section>

          <section id="calendar" className="season-block">
            <h2>{t('season.calendar')}</h2>
            <p className="muted note">
              {t('calendar.timesNote', { zone: currentTimeZone().replaceAll('_', ' ') })}
              {data.voted_slots > 0 && <> · {t('calendar.votedSlots', { count: data.voted_slots })}</>}
            </p>
            {data.rounds.length === 0 ? (
              <p>{t('season.noRounds')}</p>
            ) : (
              <div className="table-wrap">
                <table className="calendar-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('season.round')}</th>
                      <th scope="col">{t('season.track')}</th>
                      <th scope="col">{t('season.date')}</th>
                      <th scope="col">{t('season.origin')}</th>
                      {adminView && <th scope="col">{t('roundTools.actions')}</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rounds.map((round) => (
                      <tr
                        key={round.id}
                        className={
                          round.cancelled ? 'cancelled-round' : round.id === next?.id ? 'next-row' : undefined
                        }
                      >
                        <td className="pos">{round.number}</td>
                        <td>
                          <Link to={`/rounds/${round.id}`}>
                            {round.track_name} · {round.layout_name}
                          </Link>
                          {round.id === next?.id && <span className="badge status-badge new">{t('dashboard.next')}</span>}
                          {round.cancelled && (
                            <span className="badge" title={round.cancel_reason}>
                              {t('roundTools.cancelled')}
                            </span>
                          )}
                          {round.track_changes.map((change, index) => (
                            <div key={index} className="muted">
                              {t('roundTools.changed', { old: change.old_layout, reason: change.reason })}
                            </div>
                          ))}
                        </td>
                        <td>
                          {round.scheduled_at
                            ? formatDateTime(round.scheduled_at, i18n.language)
                            : t('calendar.noDate')}
                        </td>
                        <td>
                          <span className="badge">{t(`season.origins.${round.origin}`)}</span>
                        </td>
                        {adminView && (
                          <td>
                            <RoundTools round={round} onChange={season.reload} />
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {adminView && (
              <AdminBlock title={t('seasonAdmin.calendar')}>
                <CalendarAdmin season={data} onChange={season.reload} />
                <ConditionsPoolForm seasonId={seasonId} />
                <CloneSeasonForm seasonId={seasonId} />
              </AdminBlock>
            )}
          </section>

          <section id="ballots" className="season-block">
            <BallotsSection seasonId={seasonId} championshipId={data.championship_id} adminView={adminView} />
          </section>

          <section id="rules" className="season-block">
            <RulesSection seasonId={seasonId} adminView={adminView} />
          </section>

          <section id="report" className="season-block">
            <ReportSection target={{ kind: 'season', id: seasonId }} adminView={adminView} />
          </section>

          <section id="entries" className="season-block">
            <h2>{t('season.entries')}</h2>
            {data.entries.length === 0 ? (
              <p>{t('season.noEntries')}</p>
            ) : (
              <ul className="entry-grid">
                {data.entries.map((entry) => (
                  <li key={entry.id}>
                    <span className="entry-number">{entry.number}</span>
                    <span>
                      <b>{entry.driver_name}</b>
                      <span className="muted">{entry.car_name}</span>
                      {entry.team && <span className="entry-team">{entry.team}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {adminView && (
              <AdminBlock title={t('seasonAdmin.entries')}>
                <SeasonForms seasonId={seasonId} onChange={season.reload} />
                <div className="forms">
                  <ActionForm
                    title={t('season.settings')}
                    submitLabel={t('common.save')}
                    onSubmit={async (form) => {
                      const { error } = await api.PATCH('/api/seasons/{season_id}/settings', {
                        params: { path },
                        body: {
                          protest_window_minutes: Number(form.get('protest_window_minutes')),
                          allow_repeat_layouts: form.get('allow_repeat_layouts') === 'on',
                        },
                      })
                      if (!error) season.reload()
                      return error
                    }}
                  >
                    <label>
                      {t('season.protestWindow')}
                      <input
                        name="protest_window_minutes"
                        type="number"
                        min={0}
                        max={10080}
                        required
                        defaultValue={data.protest_window_minutes}
                      />
                    </label>
                    <label className="check">
                      <input
                        type="checkbox"
                        name="allow_repeat_layouts"
                        defaultChecked={data.allow_repeat_layouts}
                      />
                      {t('calendar.allowRepeats')}
                    </label>
                  </ActionForm>
                </div>
              </AdminBlock>
            )}
          </section>
        </div>
      </div>
    </section>
  )
}

/** Admin forms of a section, folded so that the season reads first. */
function AdminBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="admin-block">
      <summary>
        <Icon name="shield" small />
        {title}
      </summary>
      <div className="admin-block-body">{children}</div>
    </details>
  )
}

function SeasonForms({ seasonId, onChange }: { seasonId: number; onChange: () => void }) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const drivers = useLoad(() => api.GET('/api/drivers'), [])

  return (
    <div className="forms">
      <ActionForm
        title={t('season.addRound')}
        submitLabel={t('common.add')}
        onSubmit={async (form) => {
          const { error } = await api.POST('/api/seasons/{season_id}/rounds', {
            params: { path },
            body: {
              track_layout_id: Number(form.get('track_layout_id')),
              scheduled_at: localInputToIso(String(form.get('scheduled_at'))),
            },
          })
          if (!error) onChange()
          return error
        }}
      >
        <label>
          {t('season.layout')}
          <select name="track_layout_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {tracks.data?.map((track) =>
              track.layouts.map((layout) => (
                <option key={layout.id} value={layout.id}>
                  {track.name} · {layout.name}
                </option>
              )),
            )}
          </select>
        </label>
        <label>
          {t('season.date')}
          <input name="scheduled_at" type="datetime-local" required />
        </label>
      </ActionForm>

      <ActionForm
        title={t('season.addEntry')}
        submitLabel={t('common.add')}
        onSubmit={async (form) => {
          const { error } = await api.POST('/api/seasons/{season_id}/entries', {
            params: { path },
            body: {
              driver_id: Number(form.get('driver_id')),
              car_id: Number(form.get('car_id')),
              number: Number(form.get('number')),
              team: String(form.get('team') ?? ''),
            },
          })
          if (!error) onChange()
          return error
        }}
      >
        <label>
          {t('season.driver')}
          <select name="driver_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {drivers.data?.map((driver) => (
              <option key={driver.id} value={driver.id}>
                {driver.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('season.car')}
          <select name="car_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {cars.data?.map((car) => (
              <option key={car.id} value={car.id}>
                {car.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('season.number')}
          <input name="number" type="number" min={1} max={999} required />
        </label>
        <label>
          {t('season.team')}
          <input name="team" maxLength={100} />
        </label>
      </ActionForm>
    </div>
  )
}
