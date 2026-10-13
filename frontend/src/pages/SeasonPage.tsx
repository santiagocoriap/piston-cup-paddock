import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { AdminActions } from '../components/AdminActions'
import { Icon } from '../components/Icon'
import { RowMenu } from '../components/RowMenu'
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
import { Breadcrumbs } from '../components/Breadcrumbs'

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
  const active = useActiveSection(SECTIONS, data !== undefined)
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
  const labels: Record<(typeof SECTIONS)[number], string> = {
    standings: t('standings.title'),
    title: t('seasonNav.title'),
    safety: t('seasonNav.safety'),
    handicaps: t('seasonNav.handicaps'),
    calendar: t('season.calendar'),
    ballots: t('seasonNav.ballots'),
    rules: t('seasonNav.rules'),
    report: t('seasonNav.report'),
    entries: t('season.entries'),
  }
  const roundStatus = (round: (typeof data.rounds)[number]) =>
    round.cancelled
      ? 'cancelled'
      : round.id === next?.id
        ? 'next'
        : round.scheduled_at && new Date(round.scheduled_at).getTime() <= now
          ? 'done'
          : 'later'

  return (
    <section className="season-page">
      <Breadcrumbs
        items={[{ label: data.championship_name, to: `/championships/${data.championship_id}` }, { label: data.name }]}
      />
      <header className="season-hero">
        <div>
          <h1 className="season-title">{data.name}</h1>
          <div className="season-actions">
            <RowMenu
              label={t('season.download')}
              trigger={
                <>
                  <Icon name="download" small />
                  {t('season.download')}
                  <Icon name="chevron" small />
                </>
              }
              items={[
                { label: t('season.downloads.calendar'), href: `/api/seasons/${seasonId}/calendar.ics` },
                ...(['results', 'standings', 'restarts'] as const).map((kind) => ({
                  label: t('season.downloads.csv', { name: t(`exports.${kind}`) }),
                  href: `/api/seasons/${seasonId}/export/${kind}.csv`,
                })),
              ]}
            />
            {adminView && (
              <AdminActions
                actions={[
                  {
                    id: 'settings',
                    label: t('season.settings'),
                    content: (close) => <SeasonSettingsForm season={data} onChange={season.reload} onDone={close} />,
                  },
                ]}
              />
            )}
          </div>
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
                  {t('season.roundLabel', { number: next.number })} · {next.track_name}
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
          {SECTIONS.map((id) => (
            <a
              key={id}
              href={`#${id}`}
              className={active === id ? 'active' : undefined}
              aria-current={active === id ? 'location' : undefined}
            >
              {labels[id]}
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
            <div className="section-head">
              <h2>{t('season.calendar')}</h2>
              {adminView && (
                <AdminActions
                  actions={[
                    {
                      id: 'round',
                      label: t('season.addRound'),
                      content: (close) => <AddRoundForm seasonId={seasonId} onChange={season.reload} onDone={close} />,
                    },
                    {
                      id: 'fixed',
                      label: t('calendar.fixed'),
                      content: (close) => (
                        <CalendarAdmin season={data} onChange={season.reload} only="fixed" onDone={close} />
                      ),
                    },
                    ...(data.rounds.length > 0
                      ? [
                          {
                            id: 'edit',
                            label: t('calendar.edit'),
                            content: (close: () => void) => (
                              <CalendarAdmin season={data} onChange={season.reload} only="edit" onDone={close} />
                            ),
                          },
                        ]
                      : []),
                    {
                      id: 'pool',
                      label: t('draw.poolTitle'),
                      content: (close) => <ConditionsPoolForm seasonId={seasonId} onDone={close} />,
                    },
                    {
                      id: 'clone',
                      label: t('roundTools.cloneTitle'),
                      content: (close) => <CloneSeasonForm seasonId={seasonId} onDone={close} />,
                    },
                  ]}
                />
              )}
            </div>
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
                      {adminView && (
                        <th scope="col" className="row-actions">
                          <span className="sr-only">{t('roundTools.actions')}</span>
                        </th>
                      )}
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
                        <td className="pos">
                          <span className="round-status">
                            <span className={`round-dot ${roundStatus(round)}`} aria-hidden="true" />
                            {round.number}
                            <span className="sr-only">{t(`calendar.status.${roundStatus(round)}`)}</span>
                          </span>
                        </td>
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
                          <td className="row-actions">
                            <RoundTools round={round} onChange={season.reload} />
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
            <div className="section-head">
              <h2>{t('season.entries')}</h2>
              {adminView && (
                <AdminActions
                  actions={[
                    {
                      id: 'entry',
                      label: t('season.addEntry'),
                      content: (close) => <AddEntryForm seasonId={seasonId} onChange={season.reload} onDone={close} />,
                    },
                  ]}
                />
              )}
            </div>
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
          </section>
        </div>
      </div>
    </section>
  )
}

type FormProps = { seasonId: number; onChange: () => void; onDone: () => void }

/** The sections of the page, in order. The side navigation links to them. */
const SECTIONS = ['standings', 'title', 'safety', 'handicaps', 'calendar', 'ballots', 'rules', 'report', 'entries'] as const

/** The section at the top of the screen, for the side navigation. */
function useActiveSection(ids: readonly string[], ready: boolean): string {
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    if (!ready || typeof IntersectionObserver === 'undefined') return
    const visible = new Map<string, boolean>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) visible.set(entry.target.id, entry.isIntersecting)
        const first = ids.find((id) => visible.get(id))
        if (first) setActive(first)
      },
      // A section counts when it crosses the top third of the screen.
      { rootMargin: '-80px 0px -66% 0px' },
    )
    for (const id of ids) {
      const element = document.getElementById(id)
      if (element) observer.observe(element)
    }
    return () => observer.disconnect()
  }, [ids, ready])
  return active
}

function SeasonSettingsForm({
  season,
  onChange,
  onDone,
}: {
  season: components['schemas']['SeasonDetail']
  onChange: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  return (
    <ActionForm
      title={t('season.settings')}
      submitLabel={t('common.save')}
      onDone={onDone}
      onSubmit={async (form) => {
        const { error } = await api.PATCH('/api/seasons/{season_id}/settings', {
          params: { path: { season_id: season.id } },
          body: {
            protest_window_minutes: Number(form.get('protest_window_minutes')),
            allow_repeat_layouts: form.get('allow_repeat_layouts') === 'on',
          },
        })
        if (!error) onChange()
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
          defaultValue={season.protest_window_minutes}
        />
      </label>
      <label className="check">
        <input type="checkbox" name="allow_repeat_layouts" defaultChecked={season.allow_repeat_layouts} />
        {t('calendar.allowRepeats')}
      </label>
    </ActionForm>
  )
}

function AddRoundForm({ seasonId, onChange, onDone }: FormProps) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  return (
    <ActionForm
      title={t('season.addRound')}
      submitLabel={t('common.add')}
      onDone={onDone}
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
  )
}

function AddEntryForm({ seasonId, onChange, onDone }: FormProps) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  return (
    <ActionForm
      title={t('season.addEntry')}
      submitLabel={t('common.add')}
      onDone={onDone}
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
  )
}
