import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { AdminActions, type AdminAction } from '../components/AdminActions'
import { Avatar } from '../components/Avatar'
import { Icon, type IconName } from '../components/Icon'
import { Loading } from '../components/Layout'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { BallotOptionPicker } from './BallotOptionPicker'
import { useAdminView } from '../session'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { DangerMenu } from '../components/DangerMenu'
import { BallotSettingsForm } from './BallotSettingsForm'

type Ballot = components['schemas']['BallotDetail']
type Option = Ballot['options'][number]
type Tile = { key: string; icon: IconName; text: string; tone?: 'warn' }

export function BallotPage() {
  const { t } = useTranslation()
  const ballotId = Number(useParams().ballotId)
  const ballot = useLoad(
    () => api.GET('/api/ballots/{ballot_id}', { params: { path: { ballot_id: ballotId } } }),
    [ballotId],
  )
  const data = ballot.data
  const adminView = useAdminView(data?.can_manage ?? false)
  if (!data) return <Loading failed={ballot.failed} />
  const openRunoff = data.runoffs.find((runoff) => runoff.status === 'open')

  return (
    <section className="ballot-page">
      <Breadcrumbs
        items={[
          { label: data.championship_name, to: `/championships/${data.championship_id}` },
          { label: data.season_name, to: `/seasons/${data.season_id}` },
          { label: data.title },
        ]}
      />
      <BallotHeader ballot={data} adminView={adminView} onChange={ballot.reload} />

      {openRunoff && (
        <div className="runoff-banner" role="status">
          <Icon name="swap" />
          <p>
            <b>{t('voting.runoffOpen')}</b>
            <span>{openRunoff.title}</span>
          </p>
          <Link className="button-link" to={`/ballots/${openRunoff.id}`}>
            {t('voting.goRunoff')}
          </Link>
        </div>
      )}

      {adminView && <TieCard ballot={data} onChange={ballot.reload} />}

      <RuleTiles ballot={data} />

      {data.can_vote ? <VoteGrid ballot={data} onVoted={ballot.reload} /> : <Results ballot={data} />}
      {data.status === 'decided' && data.kind === 'track' && !data.parent && (
        <p className="callout">
          {t('voting.inCalendar')}{' '}
          <Link to={`/seasons/${data.season_id}#calendar`}>{t('voting.toCalendar')}</Link>
        </p>
      )}

      {data.runoffs.length > 0 && (
        <section aria-labelledby="runoffs">
          <h2 id="runoffs">{t('voting.runoffs')}</h2>
          <ul className="runoff-cards">
            {data.runoffs.map((runoff) => (
              <li key={runoff.id}>
                <Link to={`/ballots/${runoff.id}`}>{runoff.title}</Link>
                <span className={`badge ballot-${runoff.status}`}>{t(`voting.status.${runoff.status}`)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {adminView && <VotersTable ballot={data} />}
    </section>
  )
}

/** The time left until a date, in days, hours, and minutes. It updates each minute. */
function useTimeLeft(iso: string | null | undefined) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!iso) return
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [iso])
  if (!iso) return null
  const left = Math.max(0, new Date(iso).getTime() - now)
  return {
    days: Math.floor(left / 86_400_000),
    hours: Math.floor((left % 86_400_000) / 3_600_000),
    minutes: Math.floor((left % 3_600_000) / 60_000),
    done: left === 0,
  }
}

function BallotHeader({ ballot, adminView, onChange }: { ballot: Ballot; adminView: boolean; onChange: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const left = useTimeLeft(ballot.status === 'open' ? ballot.closes_at : null)
  const share = ballot.voter_count ? Math.round((ballot.voted_count / ballot.voter_count) * 100) : 0
  return (
    <header className="ballot-hero">
      <div className="ballot-hero-main">
        <p className="eyebrow">
          <span className={`badge ballot-${ballot.status}`}>{t(`voting.status.${ballot.status}`)}</span>
          <span>{t('voting.kindTitle', { kind: t(`voting.kind.${ballot.kind}`) })}</span>
        </p>
        <h1>{ballot.title}</h1>
        {adminView && (
          <div className="season-actions">
            <DangerMenu
              target={{ kind: 'ballot', id: ballot.id, name: ballot.title }}
              onDeleted={() => navigate(`/seasons/${ballot.season_id}`)}
              wide
            />
          </div>
        )}
        {ballot.parent && (
          <p>
            <Link to={`/ballots/${ballot.parent.id}`}>{t('voting.parent', { title: ballot.parent.title })}</Link>
          </p>
        )}
        {ballot.status !== 'draft' && (
          <div className="participation">
            <p>
              <b>{t('voting.participation', { voted: ballot.voted_count, total: ballot.voter_count })}</b>
              <span className="muted">{share} %</span>
            </p>
            <div
              className="participation-bar"
              role="progressbar"
              aria-label={t('voting.participationLabel')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={share}
            >
              <span style={{ width: `${share}%` }} />
            </div>
          </div>
        )}
      </div>
      <div className="ballot-hero-side">
        {left && !left.done && (
          <div className="ballot-countdown" aria-label={t('voting.closesIn', left)}>
            <span className="muted">{t('voting.closesInLabel')}</span>
            <p aria-hidden="true">
              {left.days > 0 && (
                <span>
                  <b>{left.days}</b>
                  <small>{t('dashboard.days', { count: left.days })}</small>
                </span>
              )}
              <span>
                <b>{left.hours}</b>
                <small>{t('dashboard.hours', { count: left.hours })}</small>
              </span>
              <span>
                <b>{left.minutes}</b>
                <small>min</small>
              </span>
            </p>
          </div>
        )}
        {adminView && <BallotAdmin ballot={ballot} onChange={onChange} />}
      </div>
    </header>
  )
}

/** The rules of the ballot as small tiles with an icon. */
function RuleTiles({ ballot }: { ballot: Ballot }) {
  const { t, i18n } = useTranslation()
  const tiles: Tile[] = [
    { key: 'method', icon: 'check', text: t(`voting.method.${ballot.method}`, { count: ballot.selection_limit }) },
    {
      key: 'slots',
      icon: 'flag',
      text: ballot.kind === 'track' ? t('voting.slotsTrack', { count: ballot.slots }) : `${t('voting.slots')}: ${ballot.slots}`,
    },
    { key: 'totals', icon: 'layers', text: t(`voting.totals.${ballot.totals_visibility}`) },
    {
      key: 'choices',
      icon: 'users',
      text: `${t(`voting.choices.${ballot.choice_visibility}`)} ${t('voting.adminNote')}`,
    },
    {
      key: 'changes',
      icon: ballot.allow_vote_changes ? 'rotate' : 'lock',
      text: ballot.allow_vote_changes ? t('voting.allowChanges') : t('voting.noChanges'),
    },
  ]
  if (ballot.opens_at && ballot.status === 'draft')
    tiles.push({ key: 'opens', icon: 'clock', text: t('voting.opensAt', { date: formatDateTime(ballot.opens_at, i18n.language) }) })
  if (ballot.closes_at)
    tiles.push({ key: 'closes', icon: 'clock', text: t('voting.closesAt', { date: formatDateTime(ballot.closes_at, i18n.language) }) })
  if (ballot.remind_hours_before > 0 && ballot.closes_at)
    tiles.push({ key: 'remind', icon: 'bell', text: t('voting.reminder', { count: ballot.remind_hours_before }) })
  if (ballot.min_participation_pct > 0)
    tiles.push({
      key: 'participation',
      icon: 'users',
      text: `${t('voting.minParticipationRule', { pct: ballot.min_participation_pct })} ${t(`voting.lowActions.${ballot.low_participation_action}`)}`,
    })
  if (ballot.power_exceptions.length > 0)
    tiles.push({
      key: 'power',
      icon: 'shield',
      text: t('voting.powerExceptions', {
        list: ballot.power_exceptions.map((v) => `${v.username} ×${v.power}`).join(', '),
      }),
    })
  if (ballot.voted_names && ballot.voted_names.length > 0)
    tiles.push({ key: 'voted', icon: 'check', text: t('voting.votedNames', { names: ballot.voted_names.join(', ') }) })
  if (ballot.closed_early)
    tiles.push({ key: 'early', icon: 'alert', text: t('voting.closedEarly', { reason: ballot.close_reason }), tone: 'warn' })
  if (ballot.low_participation)
    tiles.push({ key: 'low', icon: 'alert', text: t('voting.lowParticipationHappened'), tone: 'warn' })

  return (
    <section aria-labelledby="ballot-rules">
      <h2 id="ballot-rules">{t('voting.rules')}</h2>
      <ul className="rule-tiles">
        {tiles.map((tile) => (
          <li key={tile.key} className={tile.tone === 'warn' ? 'warn' : undefined}>
            <span className="rule-icon" aria-hidden="true">
              <Icon name={tile.icon} small />
            </span>
            <span>{tile.text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The options as cards. A track option shows the picture of the track. The vote button
 * stays at the bottom of the screen while the driver chooses. */
function VoteGrid({ ballot, onVoted }: { ballot: Ballot; onVoted: () => void }) {
  const { t } = useTranslation()
  const [chosen, setChosen] = useState<number[]>(ballot.my_choices)
  const [message, setMessage] = useState<{ kind: 'error' | 'saved'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const limit = ballot.my_choice_limit || ballot.selection_limit
  const single = limit === 1

  function toggle(optionId: number) {
    setMessage(null)
    setChosen((current) => {
      if (single) return [optionId]
      return current.includes(optionId) ? current.filter((id) => id !== optionId) : [...current, optionId]
    })
  }

  async function submit() {
    setMessage(null)
    setBusy(true)
    const { error } = await api.PUT('/api/ballots/{ballot_id}/vote', {
      params: { path: { ballot_id: ballot.id } },
      body: { option_ids: chosen },
    })
    setBusy(false)
    if (error) setMessage({ kind: 'error', text: errorMessage(t, error) })
    else {
      setMessage({ kind: 'saved', text: t('voting.voted') })
      onVoted()
    }
  }

  return (
    <section aria-labelledby="vote-title">
      <div className="section-head">
        <h2 id="vote-title">{t('voting.yourVote')}</h2>
        <span className="badge power-badge">
          <Icon name="shield" small />
          {t('voting.myPower', { count: ballot.my_power })}
        </span>
      </div>
      <fieldset className="vote-grid">
        <legend className="muted">{t(`voting.method.${ballot.method}`, { count: limit })}</legend>
        {ballot.options.map((option) => {
          const checked = chosen.includes(option.id)
          const full = !single && !checked && chosen.length >= limit
          return (
            <label key={option.id} className={['vote-card', checked && 'checked', full && 'full'].filter(Boolean).join(' ')}>
              <input
                type={single ? 'radio' : 'checkbox'}
                name="option"
                checked={checked}
                disabled={full}
                onChange={() => toggle(option.id)}
              />
              <span className="vote-media" aria-hidden="true">
                {option.image_url ? <img src={option.image_url} alt="" loading="lazy" /> : <Icon name={ballot.kind === 'track' ? 'map' : 'layers'} />}
                <span className="vote-check">
                  <Icon name="check" small />
                </span>
              </span>
              <span className="vote-text">
                <b>{option.label}</b>
                {option.votes !== null && option.votes !== undefined && (
                  <span className="muted">{t('voting.votes', { count: option.votes })}</span>
                )}
                {option.voter_pictures && option.voter_pictures.length > 0 && (
                  <span className="vote-voters">
                    <span className="avatar-stack" aria-hidden="true">
                      {option.voter_pictures.slice(0, 5).map((person) => (
                        <Avatar key={person.username} name={person.username} url={person.avatar_url} />
                      ))}
                    </span>
                    <span className="muted">{option.voter_pictures.map((person) => person.username).join(', ')}</span>
                  </span>
                )}
              </span>
            </label>
          )
        })}
      </fieldset>
      <div className="vote-bar">
        <p className="vote-count">
          {single
            ? chosen.length > 0
              ? t('voting.oneChosen')
              : t('voting.chooseOne')
            : t('voting.chosenOf', { count: chosen.length, limit })}
        </p>
        {message && (
          <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
            {message.text}
          </p>
        )}
        <button type="button" onClick={submit} disabled={chosen.length === 0 || busy}>
          {t('voting.vote')}
        </button>
      </div>
    </section>
  )
}

/** The options for a user who does not vote now. With visible totals, each option is a bar
 * with its share of the votes, the most voted first. */
function Results({ ballot }: { ballot: Ballot }) {
  const { t } = useTranslation()
  const counted = ballot.options.some((option) => option.votes !== null && option.votes !== undefined)
  const total = ballot.options.reduce((sum, option) => sum + (option.votes ?? 0), 0)
  const top = Math.max(0, ...ballot.options.map((option) => option.votes ?? 0))
  const rows = counted ? [...ballot.options].sort((a, b) => (b.votes ?? 0) - (a.votes ?? 0)) : ballot.options
  return (
    <section aria-labelledby="ballot-results">
      <div className="section-head">
        <h2 id="ballot-results">{counted ? t('voting.results') : t('voting.options')}</h2>
      </div>
      {ballot.status === 'open' && ballot.my_power === 0 && <p className="muted">{t('voting.notVoter')}</p>}
      <ul className="result-bars">
        {rows.map((option) => (
          <ResultBar
            key={option.id}
            option={option}
            share={counted && total ? Math.round(((option.votes ?? 0) / total) * 100) : null}
            leader={counted && top > 0 && option.votes === top}
            mine={ballot.my_choices.includes(option.id)}
          />
        ))}
      </ul>
    </section>
  )
}

function ResultBar({ option, share, leader, mine }: { option: Option; share: number | null; leader: boolean; mine: boolean }) {
  const { t } = useTranslation()
  const won = option.selected
  return (
    <li className={['result-bar', won && 'won', leader && 'leader'].filter(Boolean).join(' ')}>
      {share !== null && <span className="result-fill" style={{ width: `${share}%` }} aria-hidden="true" />}
      <span className="result-thumb" aria-hidden="true">
        {option.image_url ? <img src={option.image_url} alt="" loading="lazy" /> : <Icon name={won ? 'trophy' : 'flag'} small />}
      </span>
      <span className="result-label">
        <b>{option.label}</b>
        <span className="result-tags">
          {won && (
            <span className="badge winner-badge">
              <Icon name="trophy" small />
              {t(`voting.source.${option.selected_by || 'vote'}`)}
            </span>
          )}
          {mine && <span className="badge">{t('voting.myChoice')}</span>}
        </span>
      </span>
      {option.voter_pictures && option.voter_pictures.length > 0 && (
        <span className="avatar-stack" aria-label={option.voter_pictures.map((person) => person.username).join(', ')}>
          {option.voter_pictures.slice(0, 5).map((person) => (
            <Avatar key={person.username} name={person.username} url={person.avatar_url} />
          ))}
          {option.voter_pictures.length > 5 && <span className="avatar more">+{option.voter_pictures.length - 5}</span>}
        </span>
      )}
      {option.voter_pictures && option.voter_pictures.length > 0 && (
        <span className="result-voters muted">{option.voter_pictures.map((person) => person.username).join(', ')}</span>
      )}
      {option.votes !== null && option.votes !== undefined && (
        <span className="result-numbers">
          <b>{share ?? 0} %</b>
          <span className="muted">{t('voting.votes', { count: option.votes })}</span>
        </span>
      )}
    </li>
  )
}

/** A tie that an admin must solve: open a runoff here, or choose by hand in the menu. */
function TieCard({ ballot, onChange }: { ballot: Ballot; onChange: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  if (ballot.status !== 'closed' || !ballot.tie) return null
  return (
    <div className="tie-card" role="status">
      <Icon name="alert" />
      <p>
        <b>{t('voting.tie', { count: ballot.tie.option_ids.length, slots: ballot.tie.open_slots })}</b>
        <span className="muted">{t('voting.tieHelp')}</span>
      </p>
      <button
        type="button"
        onClick={async () => {
          setError(null)
          const { data, error } = await api.POST('/api/ballots/{ballot_id}/runoff', { params: { path: { ballot_id: ballot.id } } })
          if (error || !data) setError(errorMessage(t, error))
          else {
            onChange()
            navigate(`/ballots/${data.id}`)
          }
        }}
      >
        {t('voting.runoff')}
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}

/** The voters for an admin, with their pictures, vote power, and state. */
function VotersTable({ ballot }: { ballot: Ballot }) {
  const { t } = useTranslation()
  if (!ballot.voters || ballot.voters.length === 0) return null
  return (
    <section aria-labelledby="ballot-voters">
      <h2 id="ballot-voters">{t('voting.voters')}</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('voting.user')}</th>
              <th scope="col" className="num">{t('voting.power')}</th>
              <th scope="col">{t('voting.state')}</th>
            </tr>
          </thead>
          <tbody>
            {ballot.voters.map((voter) => (
              <tr key={voter.username}>
                <td>
                  <span className="person">
                    <Avatar name={voter.username} url={voter.avatar_url} />
                    {voter.username}
                  </span>
                </td>
                <td className="num">×{voter.power}</td>
                <td>
                  <span className={voter.voted ? 'voted-yes' : 'voted-no'}>
                    <Icon name={voter.voted ? 'check' : 'clock'} small />
                    {voter.voted ? t('voting.didVote') : t('voting.didNotVote')}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** The admin tools in the "Administrar" menu. Each tool opens in a dialog. */
function BallotAdmin({ ballot, onChange }: { ballot: Ballot; onChange: () => void }) {
  const { t } = useTranslation()
  const path = { ballot_id: ballot.id }
  const actions: AdminAction[] = []
  const tiedOptions = ballot.options.filter((option) => ballot.tie?.option_ids.includes(option.id))
  const remaining = ballot.slots - ballot.options.filter((option) => option.selected).length

  if (ballot.status === 'draft') {
    actions.push(
      { id: 'settings', label: t('voting.settings'), content: (close) => <BallotSettingsForm ballot={ballot} onDone={() => { onChange(); close() }} /> },
      { id: 'options', label: t('optionPicker.title'), content: (close) => <BallotOptionPicker ballot={ballot} onDone={() => { onChange(); close() }} /> },
      ...(ballot.kind === 'car_class'
        ? [{ id: 'add', label: t('voting.addFreeOption'), content: (close: () => void) => <AddOptionForm ballot={ballot} onDone={() => { onChange(); close() }} /> }]
        : []),
      { id: 'power', label: t('voting.setPower'), content: (close) => <PowerForm ballot={ballot} onDone={() => { onChange(); close() }} /> },
      { id: 'open', label: t('voting.open'), content: (close) => <OpenPanel ballot={ballot} onChange={onChange} onOpened={close} /> },
    )
  }
  if (ballot.status === 'open') {
    actions.push(
      { id: 'remind', label: t('voting.remindNow'), content: (close) => <RemindPanel ballot={ballot} onDone={() => { onChange(); close() }} /> },
      {
        id: 'close',
        label: t('voting.close'),
        content: (close) => (
          <ActionForm
            title={t('voting.close')}
            submitLabel={t('voting.close')}
            onDone={() => { onChange(); close() }}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/ballots/{ballot_id}/close', {
                params: { path },
                body: { reason: String(form.get('reason') ?? '') },
              })
              return error
            }}
          >
            <label>
              {t('voting.closeReason')}
              <input name="reason" maxLength={500} />
            </label>
          </ActionForm>
        ),
      },
      { id: 'decide', label: t('voting.decide'), content: (close) => <DecideForm ballot={ballot} options={ballot.options} count={remaining} onDone={() => { onChange(); close() }} /> },
    )
  }
  if (ballot.status === 'closed' && ballot.tie) {
    actions.push({
      id: 'decide',
      label: t('voting.decide'),
      content: (close) => <DecideForm ballot={ballot} options={tiedOptions} count={ballot.tie?.open_slots ?? 0} onDone={() => { onChange(); close() }} />,
    })
  }
  return <AdminActions actions={actions} />
}

function RemindPanel({ ballot, onDone }: { ballot: Ballot; onDone: () => void }) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="card">
      <p className="muted">{ballot.reminded_at ? t('voting.reminded') : t('voting.remindHelp')}</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={async () => {
          const { error } = await api.POST('/api/ballots/{ballot_id}/remind', { params: { path: { ballot_id: ballot.id } } })
          if (error) setError(errorMessage(t, error))
          else onDone()
        }}
      >
        {t('voting.sendReminder')}
      </button>
    </div>
  )
}

function OpenPanel({ ballot, onChange, onOpened }: { ballot: Ballot; onChange: () => void; onOpened: () => void }) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  async function act(run: () => Promise<{ error?: unknown }>, after: () => void) {
    setError(null)
    const { error } = await run()
    if (error) setError(errorMessage(t, error))
    else after()
  }
  return (
    <div className="card">
      <p className="muted">{t('voting.openHelp')}</p>
      <ul className="list">
        {ballot.options.map((option) => (
          <li key={option.id} className="option-row">
            <span>{option.label}</span>
            <button
              type="button"
              className="secondary small"
              onClick={() =>
                act(
                  () =>
                    api.DELETE('/api/ballots/{ballot_id}/options/{option_id}', {
                      params: { path: { ballot_id: ballot.id, option_id: option.id } },
                    }),
                  onChange,
                )
              }
            >
              {t('voting.remove')}
            </button>
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={() =>
          act(() => api.POST('/api/ballots/{ballot_id}/open', { params: { path: { ballot_id: ballot.id } } }), () => {
            onChange()
            onOpened()
          })
        }
      >
        {t('voting.open')}
      </button>
    </div>
  )
}

function AddOptionForm({ ballot, onDone }: { ballot: Ballot; onDone: () => void }) {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const classes = useLoad(() => api.GET('/api/catalog/classes'), [])
  return (
    <ActionForm
      title={t('voting.addOption')}
      submitLabel={t('common.add')}
      onDone={onDone}
      onSubmit={async (form) => {
        const { error } = await api.POST('/api/ballots/{ballot_id}/options', {
          params: { path: { ballot_id: ballot.id } },
          body:
            ballot.kind === 'track'
              ? { track_layout_id: Number(form.get('track_layout_id')) }
              : form.get('car_class_id')
                ? { car_class_id: Number(form.get('car_class_id')) }
                : { label: String(form.get('label') ?? '') },
        })
        return error
      }}
    >
      {ballot.kind === 'track' ? (
        <label>
          {t('voting.layout')}
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
      ) : (
        <>
          {(classes.data?.length ?? 0) > 0 && (
            <label>
              {t('voting.carClass')}
              <select name="car_class_id" defaultValue="">
                <option value="">{t('voting.freeLabel')}</option>
                {classes.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            {t('voting.label')}
            <input name="label" maxLength={150} />
          </label>
        </>
      )}
    </ActionForm>
  )
}

function PowerForm({ ballot, onDone }: { ballot: Ballot; onDone: () => void }) {
  const { t } = useTranslation()
  const users = useLoad(() => api.GET('/api/users'), [])
  return (
    <ActionForm
      title={t('voting.setPower')}
      submitLabel={t('common.save')}
      onDone={onDone}
      onSubmit={async (form) => {
        const { error } = await api.PATCH('/api/ballots/{ballot_id}', {
          params: { path: { ballot_id: ballot.id } },
          body: {
            power_overrides: {
              ...ballot.power_overrides,
              [String(form.get('user_id'))]: Number(form.get('power')),
            },
            choice_overrides: {
              ...ballot.choice_overrides,
              [String(form.get('user_id'))]: Number(form.get('choices') || ballot.selection_limit),
            },
          },
        })
        return error
      }}
    >
      {Object.keys(ballot.power_overrides).length > 0 && (
        <p className="muted">
          {t('voting.powerExceptions', {
            list: Object.entries(ballot.power_overrides)
              .map(([id, power]) => `${users.data?.find((u) => u.id === Number(id))?.username ?? id} ×${power}`)
              .join(', '),
          })}
        </p>
      )}
      <div className="field-row">
        <label>
          {t('voting.user')}
          <select name="user_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {users.data?.map((user) => (
              <option key={user.id} value={user.id}>
                {user.username}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('voting.power')}
          <input name="power" type="number" min={0} max={10} defaultValue={1} required />
        </label>
        {ballot.method === 'multiple' && (
          <label>
            {t('voting.choiceLimit')}
            <input name="choices" type="number" min={1} max={50} defaultValue={ballot.selection_limit} required />
          </label>
        )}
      </div>
      <p className="muted">{t('voting.powerHelp', { count: ballot.selection_limit })}</p>
      {Object.keys(ballot.choice_overrides).length > 0 && (
        <p className="muted">
          {t('voting.choiceExceptions', {
            list: Object.entries(ballot.choice_overrides)
              .map(([id, n]) => `${users.data?.find((u) => u.id === Number(id))?.username ?? id}: ${n}`)
              .join(', '),
          })}
        </p>
      )}
    </ActionForm>
  )
}

function DecideForm({
  ballot,
  options,
  count,
  onDone,
}: {
  ballot: Ballot
  options: Ballot['options']
  count: number
  onDone: () => void
}) {
  const { t } = useTranslation()
  return (
    <ActionForm
      title={t('voting.decide')}
      submitLabel={t('voting.decide')}
      onDone={onDone}
      onSubmit={async (form) => {
        const { error } = await api.POST('/api/ballots/{ballot_id}/decide', {
          params: { path: { ballot_id: ballot.id } },
          body: {
            option_ids: form.getAll('option_ids').map(Number),
            reason: String(form.get('reason') ?? ''),
          },
        })
        return error
      }}
    >
      <p className="muted">{t('voting.decideHelp', { count })}</p>
      <fieldset className="checks">
        {options
          .filter((option) => !option.selected)
          .map((option) => (
            <label key={option.id} className="check">
              <input type="checkbox" name="option_ids" value={option.id} />
              {option.label}
            </label>
          ))}
      </fieldset>
      <label>
        {t('voting.decideReason')}
        <input name="reason" required maxLength={500} />
      </label>
    </ActionForm>
  )
}
