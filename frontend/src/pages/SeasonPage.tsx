import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { AdminActions } from '../components/AdminActions'
import { Icon } from '../components/Icon'
import { RowMenu } from '../components/RowMenu'
import { Loading } from '../components/Layout'
import { currentTimeZone, formatDateTime, localInputToIso } from '../lib/format'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'
import { medal } from '../lib/medal'
import { useAdminView } from '../session'
import { BallotsSection } from './BallotsSection'
import { CalendarAdmin } from './CalendarAdmin'
import { CalendarOrder } from './CalendarOrder'
import { ReportSection } from './ReportSection'
import { CloneSeasonForm, RoundTools } from './RoundTools'
import { RulesSection } from './RulesSection'
import { SafetySection } from './SafetySection'
import { TitleSection } from './TitleSection'
import { HandicapsSection } from './HandicapsSection'
import { ConditionsPoolForm } from './ConditionsDraw'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { Avatar } from '../components/Avatar'
import { DangerMenu } from '../components/DangerMenu'
import { useRowDrag } from '../lib/useRowDrag'
import { EntrySkinPicker } from './EntrySkinPicker'
import { EntryCarPicker } from './EntryCarPicker'
import { JoinRequestsPanel } from './JoinSeason'

export function SeasonPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const seasonId = Number(useParams().seasonId)
  const path = { season_id: seasonId }
  const season = useLoad(() => api.GET('/api/seasons/{season_id}', { params: { path } }), [seasonId])
  const standings = useLoad(
    () => api.GET('/api/seasons/{season_id}/standings', { params: { path } }),
    [seasonId],
  )

  const data = season.data
  const adminView = useAdminView(data?.can_manage ?? false)
  const [active, choose] = useActiveSection(SECTIONS, data !== undefined)
  const [orderError, setOrderError] = useState<string | null>(null)
  const drag = useRowDrag(async (from, to) => {
    if (!data) return
    const ids = data.rounds.map((round) => round.id)
    const [moved] = ids.splice(from, 1)
    ids.splice(to, 0, moved)
    setOrderError(null)
    const { error } = await api.PUT('/api/seasons/{season_id}/round-order', {
      params: { path },
      body: { round_ids: ids },
    })
    if (error) setOrderError(errorMessage(t, error))
    season.reload()
  })
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
            {adminView && (
              <DangerMenu
                target={{ kind: 'season', id: data.id, name: data.name }}
                onDeleted={() => navigate(`/championships/${data.championship_id}`)}
                wide
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
      {data.entries.length === 0 && (
        <div className="season-alert" role="status">
          <Icon name="alert" small />
          <p>
            <b>{t('season.noDriversTitle')}</b>{' '}
            {adminView ? t('season.noDriversAdmin') : t('season.noDriversDriver')}
          </p>
          {adminView && (
            <a className="button-link" href="#entries">
              {t('season.noDriversGo')}
            </a>
          )}
        </div>
      )}

      <div className="season-layout">
        <nav className="season-nav" aria-label={t('seasonNav.label')}>
          {SECTIONS.map((id) => (
            <a
              key={id}
              href={`#${id}`}
              className={active === id ? 'active' : undefined}
              aria-current={active === id ? 'location' : undefined}
              onClick={(event) => {
                event.preventDefault()
                choose(id)
              }}
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
                          <td
                            className={`pos ${medal(row.rank)}`.trim()}
                            title={shared ? t('standings.shared') : undefined}
                          >
                            <span className="pos-medal">
                              {medal(row.rank) && <Icon name="medal" small />}
                              {row.rank}
                              {shared && '='}
                            </span>
                          </td>
                          <td>
                            <span className="car-number">#{row.number}</span>
                            <Link to={`/drivers/${row.driver_id}`}>{row.driver_name}</Link>
                          </td>
                          <td className="muted hide-sm">{row.car_name}</td>
                          {row.rounds.map((score) => (
                            <td
                              key={score.round_number}
                              className={`round-col hide-sm ${medal(score.position)} ${
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
                            <span className="points-cell">
                              <span className="points-bar" aria-hidden="true">
                                <span style={{ width: `${(row.points / top) * 100}%` }} />
                              </span>
                              <span className="points">{row.points}</span>
                            </span>
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
                        <CalendarAdmin season={data} onChange={season.reload} onDone={close} />
                      ),
                    },
                    ...(data.rounds.length > 0
                      ? [
                          {
                            id: 'order',
                            label: t('calendarOrder.title'),
                            content: () => (
                              <CalendarOrder seasonId={seasonId} rounds={data.rounds} onSaved={season.reload} />
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
                    {data.rounds.map((round, index) => (
                      <tr
                        key={round.id}
                        className={[
                          round.cancelled ? 'cancelled-round' : round.id === next?.id ? 'next-row' : '',
                          drag.over === index && drag.from !== index ? 'drop-here' : '',
                          drag.from === index ? 'dragging' : '',
                        ]
                          .filter(Boolean)
                          .join(' ') || undefined}
                        {...(adminView ? drag.rowProps(index) : {})}
                      >
                        <td className="pos">
                          <span className="round-status">
                            {adminView && (
                              <span className="order-grip" title={t('calendarOrder.drag')} aria-hidden="true">
                                ⠿
                              </span>
                            )}
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
            {orderError && (
              <p role="alert" className="error calendar-moved">
                {orderError}
              </p>
            )}
          </section>

          <section id="ballots" className="season-block">
            <BallotsSection seasonId={seasonId} championshipId={data.championship_id} adminView={adminView} />
          </section>

          <section id="rules" className="season-block">
            <RulesSection seasonId={seasonId} adminView={adminView} />
          </section>

          <section id="report" className="season-block">
            <ReportSection
              target={{ kind: 'season', id: seasonId }}
              adminView={adminView}
              masthead={{ kicker: t('seasonReport.kicker'), headline: `${data.championship_name} · ${data.name}` }}
            />
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
                      content: (close) => (
                        <AddEntryForm
                          seasonId={seasonId}
                          carIds={data.car_ids}
                          entered={data.entries.map((entry) => entry.driver_id)}
                          onChange={season.reload}
                          onDone={close}
                        />
                      ),
                    },
                    {
                      id: 'teams',
                      label: t('teams.title'),
                      content: () => <TeamsPanel seasonId={seasonId} />,
                    },
                    {
                      id: 'classes',
                      label: t('seasonCars.title'),
                      content: (close) => (
                        <SeasonClassesForm
                          seasonId={seasonId}
                          current={data.car_classes.map((item) => item.id)}
                          onDone={() => {
                            season.reload()
                            close()
                          }}
                        />
                      ),
                    },
                  ]}
                />
              )}
            </div>
            <p className="muted season-classes">
              {data.car_classes.length > 0
                ? t('seasonCars.classes', { list: data.car_classes.map((item) => item.name).join(', ') })
                : t('seasonCars.anyCar')}
            </p>
            {adminView && <JoinRequestsPanel seasonId={seasonId} onChange={season.reload} />}
            {data.entries.length === 0 ? (
              <p>{t('season.noEntries')}</p>
            ) : (
              <ul className="entry-grid">
                {data.entries.map((entry) => (
                  <li key={entry.id}>
                    <Avatar name={entry.driver_name} url={entry.avatar_url} className="entry-avatar" />
                    <span>
                      <b title={entry.driver_name}>{entry.driver_name}</b>
                      <span className="muted" title={entry.car_name}>
                        {entry.car_name || t('season.noCar')}
                      </span>
                      {entry.team && <span className="entry-team">{entry.team}</span>}
                      {(entry.mine || adminView) && (
                        <EntryCarPicker entry={entry} carIds={data.car_ids} onChanged={season.reload} />
                      )}
                      <EntrySkinPicker entry={entry} canChange={entry.mine || adminView} onChanged={season.reload} />
                    </span>
                    <span className="entry-number">{entry.number}</span>
                    {adminView && (
                      <DangerMenu
                        target={{ kind: 'entry', id: entry.id, name: entry.driver_name }}
                        onDeleted={season.reload}
                      />
                    )}
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

/** The section for the side navigation, and a function that scrolls to a section on a click.
 *
 * Two rules keep the highlight on the right link:
 * - A click selects its link and scrolls to the section with a smooth movement. The selection
 *   holds until the person scrolls again. Without this rule, a click on the second section of a
 *   row ("Seguridad") highlights the first one, and a click on a short last section highlights
 *   the section above it.
 * - On a scroll, the current link stays while its section is still at the top of the screen.
 *   The first section at the top gets the highlight only when the current one leaves. */
function useActiveSection(ids: readonly string[], ready: boolean): [string, (id: string) => void] {
  const [active, setActive] = useState(ids[0])
  // "free": the scroll decides. "moving": the smooth scroll of a click runs.
  // "held": the click scroll ended, and the click choice holds until the next scroll.
  const mode = useRef<'free' | 'moving' | 'held'>('free')
  const timer = useRef(0)
  useEffect(() => {
    if (!ready || typeof IntersectionObserver === 'undefined') return
    const visible = new Map<string, boolean>()
    const update = () =>
      setActive((current) => (visible.get(current) ? current : (ids.find((id) => visible.get(id)) ?? current)))
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) visible.set(entry.target.id, entry.isIntersecting)
        if (mode.current === 'free') update()
      },
      // A section counts when it crosses the top third of the screen.
      { rootMargin: '-80px 0px -66% 0px' },
    )
    for (const id of ids) {
      const element = document.getElementById(id)
      if (element) observer.observe(element)
    }
    const onScrollEnd = () => {
      if (mode.current === 'moving') mode.current = 'held'
    }
    // A scroll after the click scroll (wheel, keys, scrollbar) ends the click choice.
    const onScroll = () => {
      if (mode.current !== 'held') return
      mode.current = 'free'
      update()
    }
    window.addEventListener('scrollend', onScrollEnd)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      observer.disconnect()
      window.removeEventListener('scrollend', onScrollEnd)
      window.removeEventListener('scroll', onScroll)
      window.clearTimeout(timer.current)
    }
  }, [ids, ready])
  const choose = (id: string) => {
    mode.current = 'moving'
    setActive(id)
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    document.getElementById(id)?.scrollIntoView?.({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    window.history.replaceState(window.history.state, '', `#${id}`)
    // Without a "scrollend" event (an old browser, or no scroll at all), the choice holds after 1 s.
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(onTimeout, 1000)
  }
  const onTimeout = () => {
    if (mode.current === 'moving') mode.current = 'held'
  }
  return [active, choose]
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
            free_join: form.get('free_join') === 'on',
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
      <label className="check">
        <input type="checkbox" name="free_join" defaultChecked={season.free_join} />
        {t('join.freeJoin')}
      </label>
      <p className="muted">{t('join.freeJoinHelp')}</p>
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

function AddEntryForm({
  seasonId,
  entered,
  carIds,
  onChange,
  onDone,
}: FormProps & { entered: number[]; carIds: number[] | null | undefined }) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  const teams = useLoad(() => api.GET('/api/seasons/{season_id}/teams', { params: { path } }), [seasonId])
  // A team of the league, or a new name: the new name becomes a team of the league.
  const [team, setTeam] = useState('')
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
            car_id: form.get('car_id') ? Number(form.get('car_id')) : null,
            number: Number(form.get('number')),
            team: team === NEW_TEAM ? String(form.get('team_new') ?? '') : team,
          },
        })
        if (!error) {
          onChange()
          teams.reload()
        }
        return error
      }}
    >
      <label>
        {t('season.driver')}
        <select name="driver_id" required defaultValue="">
          <option value="" disabled>
            {t('common.select')}
          </option>
          {drivers.data?.filter((driver) => !entered.includes(driver.id)).map((driver) => (
            <option key={driver.id} value={driver.id}>
              {driver.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('season.car')}
        <select name="car_id" defaultValue="">
          <option value="">{t('season.carLater')}</option>
          {cars.data
            ?.filter((car) => !carIds || carIds.includes(car.id))
            .map((car) => (
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
        <select value={team} onChange={(event) => setTeam(event.target.value)}>
          <option value="">{t('teams.none')}</option>
          {teams.data?.map((item) => (
            <option key={item.id} value={item.name}>
              {item.name}
            </option>
          ))}
          <option value={NEW_TEAM}>{t('teams.new')}</option>
        </select>
      </label>
      {team === NEW_TEAM && (
        <label>
          {t('teams.newName')}
          <input name="team_new" maxLength={100} required autoFocus />
        </label>
      )}
    </ActionForm>
  )
}

const NEW_TEAM = '__new__'

/** The teams of the league, for an admin: add one, or remove one from the list. */
function TeamsPanel({ seasonId }: { seasonId: number }) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const teams = useLoad(() => api.GET('/api/seasons/{season_id}/teams', { params: { path } }), [seasonId])
  const [error, setError] = useState<string | null>(null)
  return (
    <ActionForm
      title={t('teams.title')}
      submitLabel={t('common.add')}
      onSubmit={async (form) => {
        const { error } = await api.POST('/api/seasons/{season_id}/teams', {
          params: { path },
          body: { name: String(form.get('name') ?? '') },
        })
        if (!error) teams.reload()
        return error
      }}
    >
      <p className="muted">{t('teams.help')}</p>
      <ul className="team-list">
        {teams.data?.map((item) => (
          <li key={item.id}>
            <span>{item.name}</span>
            <button
              type="button"
              className="link-button"
              onClick={async () => {
                setError(null)
                const { error } = await api.DELETE('/api/teams/{team_id}', { params: { path: { team_id: item.id } } })
                if (error) setError(errorMessage(t, error))
                else teams.reload()
              }}
            >
              {t('teams.remove')}
            </button>
          </li>
        ))}
        {teams.data?.length === 0 && <li className="muted">{t('teams.empty')}</li>}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <label>
        {t('teams.newName')}
        <input name="name" maxLength={100} required />
      </label>
    </ActionForm>
  )
}

/** The car classes of the season. An entry can use only a car of these classes. None: any car. */
function SeasonClassesForm({ seasonId, current, onDone }: { seasonId: number; current: number[]; onDone: () => void }) {
  const { t } = useTranslation()
  const classes = useLoad(() => api.GET('/api/catalog/classes'), [])
  return (
    <ActionForm
      title={t('seasonCars.title')}
      submitLabel={t('common.save')}
      onDone={onDone}
      onSubmit={async (form) => {
        const { error } = await api.PUT('/api/seasons/{season_id}/car-classes', {
          params: { path: { season_id: seasonId } },
          body: { class_ids: form.getAll('class_ids').map(Number) },
        })
        return error
      }}
    >
      <p className="muted">{t('seasonCars.help')}</p>
      <fieldset className="checks">
        <legend className="sr-only">{t('seasonCars.title')}</legend>
        {classes.data?.map((item) => (
          <label key={item.id} className="check">
            <input type="checkbox" name="class_ids" value={item.id} defaultChecked={current.includes(item.id)} />
            {item.name} <span className="muted">({t('seasonCars.cars', { count: item.car_ids.length })})</span>
          </label>
        ))}
      </fieldset>
    </ActionForm>
  )
}

