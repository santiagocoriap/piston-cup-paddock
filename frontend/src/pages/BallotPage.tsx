import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { Loading } from '../components/Layout'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useAdminView } from '../session'

type Ballot = components['schemas']['BallotDetail']

export function BallotPage() {
  const { t, i18n } = useTranslation()
  const ballotId = Number(useParams().ballotId)
  const ballot = useLoad(
    () => api.GET('/api/ballots/{ballot_id}', { params: { path: { ballot_id: ballotId } } }),
    [ballotId],
  )
  const data = ballot.data
  const adminView = useAdminView(data?.can_manage ?? false)
  if (!data) return <Loading failed={ballot.failed} />

  return (
    <section>
      <p className="muted">
        {data.championship_name} · <Link to={`/seasons/${data.season_id}`}>{data.season_name}</Link>
      </p>
      <h1>
        {data.title} <span className={`badge ballot-${data.status}`}>{t(`voting.status.${data.status}`)}</span>
      </h1>
      {data.parent && (
        <p>
          <Link to={`/ballots/${data.parent.id}`}>{t('voting.parent', { title: data.parent.title })}</Link>
        </p>
      )}

      <ul className="rules-list">
        <li>{t(`voting.method.${data.method}`, { count: data.selection_limit })}</li>
        <li>
          {data.kind === 'track' ? t('voting.slotsTrack', { count: data.slots }) : `${t('voting.slots')}: ${data.slots}`}
        </li>
        <li>{t(`voting.totals.${data.totals_visibility}`)}</li>
        <li>
          {t(`voting.choices.${data.choice_visibility}`)} {t('voting.adminNote')}
        </li>
        <li>{data.allow_vote_changes ? t('voting.allowChanges') : t('voting.noChanges')}</li>
        {data.opens_at && data.status === 'draft' && (
          <li>{t('voting.opensAt', { date: formatDateTime(data.opens_at, i18n.language) })}</li>
        )}
        {data.closes_at && <li>{t('voting.closesAt', { date: formatDateTime(data.closes_at, i18n.language) })}</li>}
        {data.remind_hours_before > 0 && data.closes_at && (
          <li>{t('voting.reminder', { count: data.remind_hours_before })}</li>
        )}
        {data.min_participation_pct > 0 && (
          <li>
            {t('voting.minParticipationRule', { pct: data.min_participation_pct })}{' '}
            {t(`voting.lowActions.${data.low_participation_action}`)}
          </li>
        )}
        {data.low_participation && <li className="warning">{t('voting.lowParticipationHappened')}</li>}
        {data.voted_names && data.voted_names.length > 0 && (
          <li>{t('voting.votedNames', { names: data.voted_names.join(', ') })}</li>
        )}
        {data.power_exceptions.length > 0 && (
          <li>
            {t('voting.powerExceptions', {
              list: data.power_exceptions.map((v) => `${v.username} ×${v.power}`).join(', '),
            })}
          </li>
        )}
        {data.status !== 'draft' && (
          <li>{t('voting.participation', { voted: data.voted_count, total: data.voter_count })}</li>
        )}
        {data.closed_early && <li>{t('voting.closedEarly', { reason: data.close_reason })}</li>}
      </ul>

      {data.status === 'open' && (data.my_power > 0 ? (
        <p>
          <strong>{t('voting.myPower', { count: data.my_power })}</strong>
        </p>
      ) : (
        <p className="muted">{t('voting.notVoter')}</p>
      ))}

      {data.can_vote ? (
        <VoteForm ballot={data} onVoted={ballot.reload} />
      ) : (
        <Options ballot={data} />
      )}

      {data.runoffs.length > 0 && (
        <>
          <h2>{t('voting.runoffs')}</h2>
          <ul className="list">
            {data.runoffs.map((runoff) => (
              <li key={runoff.id}>
                <Link to={`/ballots/${runoff.id}`}>{runoff.title}</Link>{' '}
                <span className="badge">{t(`voting.status.${runoff.status}`)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {adminView && <AdminPanel ballot={data} onChange={ballot.reload} />}
    </section>
  )
}

function Options({ ballot }: { ballot: Ballot }) {
  const { t } = useTranslation()
  return (
    <ul className="options">
      {ballot.options.map((option) => (
        <li key={option.id} className={option.selected ? 'selected' : undefined}>
          <span className="option-label">{option.label}</span>
          {option.votes !== null && option.votes !== undefined && (
            <span className="muted"> · {t('voting.votes', { count: option.votes })}</span>
          )}
          {option.selected && (
            <span className="badge">{t(`voting.source.${option.selected_by || 'vote'}`)}</span>
          )}
          {ballot.my_choices.includes(option.id) && <span className="badge">{t('voting.myChoice')}</span>}
          {option.voters && option.voters.length > 0 && (
            <span className="muted"> · {option.voters.join(', ')}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

function VoteForm({ ballot, onVoted }: { ballot: Ballot; onVoted: () => void }) {
  const { t } = useTranslation()
  const [chosen, setChosen] = useState<number[]>(ballot.my_choices)
  const [message, setMessage] = useState<{ kind: 'error' | 'saved'; text: string } | null>(null)
  const single = ballot.selection_limit === 1

  function toggle(optionId: number) {
    setChosen((current) => {
      if (single) return [optionId]
      return current.includes(optionId) ? current.filter((id) => id !== optionId) : [...current, optionId]
    })
  }

  async function submit() {
    setMessage(null)
    const { error } = await api.PUT('/api/ballots/{ballot_id}/vote', {
      params: { path: { ballot_id: ballot.id } },
      body: { option_ids: chosen },
    })
    if (error) setMessage({ kind: 'error', text: errorMessage(t, error) })
    else {
      setMessage({ kind: 'saved', text: t('voting.voted') })
      onVoted()
    }
  }

  return (
    <fieldset className="card vote">
      <legend>{t(`voting.method.${ballot.method}`, { count: ballot.selection_limit })}</legend>
      {ballot.options.map((option) => (
        <label key={option.id} className="check">
          <input
            type={single ? 'radio' : 'checkbox'}
            name="option"
            checked={chosen.includes(option.id)}
            disabled={!single && !chosen.includes(option.id) && chosen.length >= ballot.selection_limit}
            onChange={() => toggle(option.id)}
          />
          {option.label}
          {option.votes !== null && option.votes !== undefined && (
            <span className="muted"> · {t('voting.votes', { count: option.votes })}</span>
          )}
        </label>
      ))}
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
          {message.text}
        </p>
      )}
      <button type="button" onClick={submit} disabled={chosen.length === 0}>
        {t('voting.vote')}
      </button>
    </fieldset>
  )
}

function AdminPanel({ ballot, onChange }: { ballot: Ballot; onChange: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const path = { ballot_id: ballot.id }
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const users = useLoad(() => api.GET('/api/users'), [])
  const [error, setError] = useState<string | null>(null)

  async function act(run: () => Promise<{ error?: unknown }>) {
    setError(null)
    const { error } = await run()
    if (error) setError(errorMessage(t, error))
    else onChange()
  }

  const tiedOptions = ballot.options.filter((option) => ballot.tie?.option_ids.includes(option.id))
  const remaining = ballot.slots - ballot.options.filter((option) => option.selected).length

  return (
    <div className="admin-panel">
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {ballot.status === 'open' && (
        <p>
          <button
            type="button"
            className="secondary"
            onClick={() => act(() => api.POST('/api/ballots/{ballot_id}/remind', { params: { path } }))}
          >
            {t('voting.remindNow')}
          </button>
          {ballot.reminded_at && <span className="muted"> {t('voting.reminded')}</span>}
        </p>
      )}

      {ballot.status === 'draft' && (
        <div className="forms">
          <ActionForm
            title={t('voting.addOption')}
            submitLabel={t('common.add')}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/ballots/{ballot_id}/options', {
                params: { path },
                body:
                  ballot.kind === 'track'
                    ? { track_layout_id: Number(form.get('track_layout_id')) }
                    : { label: String(form.get('label') ?? '') },
              })
              if (!error) onChange()
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
              <label>
                {t('voting.label')}
                <input name="label" required maxLength={150} />
              </label>
            )}
          </ActionForm>

          <ActionForm
            title={t('voting.setPower')}
            submitLabel={t('common.save')}
            onSubmit={async (form) => {
              const { error } = await api.PATCH('/api/ballots/{ballot_id}', {
                params: { path },
                body: {
                  power_overrides: {
                    ...ballot.power_overrides,
                    [String(form.get('user_id'))]: Number(form.get('power')),
                  },
                },
              })
              if (!error) onChange()
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
                <input name="power" type="number" min={0} max={10} defaultValue={2} required />
              </label>
            </div>
          </ActionForm>

          <div className="card">
            <h3>{t('voting.open')}</h3>
            <p className="muted">{t('voting.openHelp')}</p>
            <ul className="list">
              {ballot.options.map((option) => (
                <li key={option.id}>
                  {option.label}{' '}
                  <button
                    type="button"
                    className="secondary small"
                    onClick={() =>
                      act(() =>
                        api.DELETE('/api/ballots/{ballot_id}/options/{option_id}', {
                          params: { path: { ballot_id: ballot.id, option_id: option.id } },
                        }),
                      )
                    }
                  >
                    {t('voting.remove')}
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => act(() => api.POST('/api/ballots/{ballot_id}/open', { params: { path } }))}>
              {t('voting.open')}
            </button>
          </div>
        </div>
      )}

      {ballot.status === 'open' && (
        <div className="forms">
          <ActionForm
            title={t('voting.close')}
            submitLabel={t('voting.close')}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/ballots/{ballot_id}/close', {
                params: { path },
                body: { reason: String(form.get('reason') ?? '') },
              })
              if (!error) onChange()
              return error
            }}
          >
            <label>
              {t('voting.closeReason')}
              <input name="reason" maxLength={500} />
            </label>
          </ActionForm>
          <DecideForm ballot={ballot} options={ballot.options} count={remaining} onChange={onChange} />
        </div>
      )}

      {ballot.status === 'closed' && ballot.tie && (
        <div className="forms">
          <div className="card">
            <h3>{t('voting.tie', { count: ballot.tie.option_ids.length, slots: ballot.tie.open_slots })}</h3>
            <button
              type="button"
              onClick={async () => {
                setError(null)
                const { data, error } = await api.POST('/api/ballots/{ballot_id}/runoff', { params: { path } })
                if (error || !data) setError(errorMessage(t, error))
                else navigate(`/ballots/${data.id}`)
              }}
            >
              {t('voting.runoff')}
            </button>
          </div>
          <DecideForm ballot={ballot} options={tiedOptions} count={ballot.tie.open_slots} onChange={onChange} />
        </div>
      )}

      {ballot.voters && ballot.voters.length > 0 && (
        <>
          <h2>{t('voting.voters')}</h2>
          <ul className="list voters">
            {ballot.voters.map((voter) => (
              <li key={voter.username}>
                {voter.username} ×{voter.power} ·{' '}
                <span className={voter.voted ? 'success' : 'muted'}>
                  {voter.voted ? t('voting.didVote') : t('voting.didNotVote')}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function DecideForm({
  ballot,
  options,
  count,
  onChange,
}: {
  ballot: Ballot
  options: Ballot['options']
  count: number
  onChange: () => void
}) {
  const { t } = useTranslation()
  return (
    <ActionForm
      title={t('voting.decide')}
      submitLabel={t('voting.decide')}
      onSubmit={async (form) => {
        const { error } = await api.POST('/api/ballots/{ballot_id}/decide', {
          params: { path: { ballot_id: ballot.id } },
          body: {
            option_ids: form.getAll('option_ids').map(Number),
            reason: String(form.get('reason') ?? ''),
          },
        })
        if (!error) onChange()
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
