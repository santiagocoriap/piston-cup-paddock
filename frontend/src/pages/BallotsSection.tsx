import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { AdminActions } from '../components/AdminActions'
import { Icon } from '../components/Icon'
import { StepForm } from '../components/StepForm'
import { localInputToIso } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type BallotIn = components['schemas']['BallotIn']
type SeasonRef = { id: number; name: string }

/** The ballots of a season, and the admin button for a new ballot. */
export function BallotsSection({
  seasonId,
  championshipId,
  adminView,
}: {
  seasonId: number
  championshipId: number
  adminView: boolean
}) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const ballots = useLoad(() => api.GET('/api/seasons/{season_id}/ballots', { params: { path } }), [seasonId])
  const championship = useLoad(
    () =>
      api.GET('/api/championships/{championship_id}', {
        params: { path: { championship_id: championshipId } },
      }),
    [championshipId],
  )
  const otherSeasons = championship.data?.seasons.filter((season) => season.id !== seasonId) ?? []

  const roots = ballots.data?.filter((ballot) => ballot.parent_id === null) ?? []
  return (
    <>
      <div className="section-head">
        <h2>{t('voting.title')}</h2>
        {adminView && (
          <AdminActions
            actions={[
              {
                id: 'new',
                label: t('voting.new'),
                content: (close) => (
                  <NewBallotForm
                    seasonId={seasonId}
                    otherSeasons={otherSeasons}
                    onDone={() => {
                      ballots.reload()
                      close()
                    }}
                  />
                ),
              },
            ]}
          />
        )}
      </div>
      {ballots.data && roots.length === 0 && <p>{t('voting.none')}</p>}
      <ul className="ballot-cards">
        {roots.map((ballot) => (
          <li key={ballot.id}>
            <Link to={`/ballots/${ballot.id}`} className="ballot-card">
              <span className="ballot-card-icon" aria-hidden="true">
                <Icon name={ballot.kind === 'track' ? 'map' : 'layers'} />
              </span>
              <span className="ballot-card-text">
                <b>{ballot.title}</b>
                <span className="ballot-card-tags">
                  <span className={`badge ballot-${ballot.status}`}>{t(`voting.status.${ballot.status}`)}</span>
                  <span className="muted">{t(`voting.kind.${ballot.kind}`)}</span>
                </span>
                {ballot.winners.length > 0 && (
                  <span className="muted">{t('voting.winners', { list: ballot.winners.join(', ') })}</span>
                )}
              </span>
              <span className="ballot-card-go">
                {t(ballot.status === 'open' ? 'voting.goVote' : 'voting.goSee')}
                <Icon name="arrow" small />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}

/** The new ballot form in 3 steps: what is voted, who sees what and when, and the advanced options. */
function NewBallotForm({
  seasonId,
  otherSeasons,
  onDone,
}: {
  seasonId: number
  otherSeasons: SeasonRef[]
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<BallotIn['kind']>('track')
  const [method, setMethod] = useState<NonNullable<BallotIn['method']>>('multiple')

  const what = (
    <>
      <label>
        {t('voting.kindLabel')}
        <select value={kind} onChange={(event) => setKind(event.target.value as BallotIn['kind'])}>
          <option value="track">{t('voting.kind.track')}</option>
          <option value="car_class">{t('voting.kind.car_class')}</option>
        </select>
      </label>
      <label>
        {t('voting.titleLabel')}
        <input name="title" required maxLength={150} />
      </label>
      <div className="field-row">
        <label>
          {t('voting.methodLabel')}
          <select value={method} onChange={(event) => setMethod(event.target.value as typeof method)}>
            <option value="multiple">{t('voting.multipleShort')}</option>
            <option value="single">{t('voting.method.single')}</option>
          </select>
        </label>
        {method === 'multiple' && (
          <label>
            {t('voting.limit')}
            <input name="selection_limit" type="number" min={1} max={50} defaultValue={3} required />
          </label>
        )}
        {kind === 'car_class' && (
          <label>
            {t('voting.slots')}
            <input name="slots" type="number" min={1} max={10} defaultValue={1} required />
          </label>
        )}
      </div>
      {kind === 'car_class' && (
        <label>
          {t('voting.classMode')}
          <select name="class_rounds" defaultValue={"one"}>
            <option value="one">{t('voting.classModes.one')}</option>
            <option value="two">{t('voting.classModes.two')}</option>
          </select>
        </label>
      )}
    </>
  )

  const who = (
    <>
      <label>
        {t('voting.totalsLabel')}
        <select name="totals_visibility" defaultValue="after_close">
          {(['live', 'after_close', 'hidden'] as const).map((value) => (
            <option key={value} value={value}>
              {t(`voting.totals.${value}`)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('voting.choicesLabel')}
        <select name="choice_visibility" defaultValue="hidden">
          {(['hidden', 'visible'] as const).map((value) => (
            <option key={value} value={value}>
              {t(`voting.choices.${value}`)}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">{t('voting.adminNote')}</p>
      <div className="field-row">
        <label>
          {t('voting.opensLabel')}
          <input name="opens_at" type="datetime-local" />
        </label>
        <label>
          {t('voting.closesLabel')}
          <input name="closes_at" type="datetime-local" />
        </label>
        <label>
          {t('voting.remindHours')}
          <input name="remind_hours_before" type="number" min={0} max={168} defaultValue={24} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" name="show_voter_names" />
        {t('voting.showVoterNames')}
      </label>
      <label className="check">
        <input type="checkbox" name="allow_vote_changes" defaultChecked />
        {t('voting.allowChanges')}
      </label>
    </>
  )

  const advanced = (
    <>
      <div className="field-row">
        <label>
          {t('voting.minParticipation')}
          <input name="min_participation_pct" type="number" min={0} max={100} defaultValue={0} />
        </label>
        <label>
          {t('voting.lowParticipation')}
          <select name="low_participation_action" defaultValue="admin">
            <option value="admin">{t('voting.lowActions.admin')}</option>
            <option value="count">{t('voting.lowActions.count')}</option>
          </select>
        </label>
        <label>
          {t('voting.maxRunoffs')}
          <input name="max_runoffs" type="number" min={0} max={20} />
        </label>
      </div>
      {otherSeasons.length > 0 && (
        <div className="field-row">
          <label>
            {t('voting.priorSeason')}
            <select name="prior_season_id" defaultValue="">
              <option value="">{t('voting.noPrior')}</option>
              {otherSeasons.map((season) => (
                <option key={season.id} value={season.id}>
                  {season.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('voting.minStarts')}
            <input name="min_prior_starts" type="number" min={0} max={100} defaultValue={0} />
          </label>
        </div>
      )}
    </>
  )

  return (
    <StepForm
      title={t('voting.new')}
      submitLabel={t('common.create')}
      onDone={onDone}
      steps={[
        { title: t('voting.steps.what'), content: what },
        { title: t('voting.steps.who'), content: who },
        { title: t('voting.steps.advanced'), content: advanced },
      ]}
      onSubmit={async (form) => {
        const closes = form.get('closes_at')
        const opens = form.get('opens_at')
        const runoffs = form.get('max_runoffs')
        const { error } = await api.POST('/api/seasons/{season_id}/ballots', {
          params: { path: { season_id: seasonId } },
          body: {
            kind,
            title: String(form.get('title')),
            method,
            selection_limit: Number(form.get('selection_limit') || 1),
            slots: kind === 'car_class' ? Number(form.get('slots') || 1) : undefined,
            class_rounds: kind === 'car_class' ? form.get('class_rounds') === 'two' : undefined,
            totals_visibility: form.get('totals_visibility') as BallotIn['totals_visibility'],
            choice_visibility: form.get('choice_visibility') as BallotIn['choice_visibility'],
            allow_vote_changes: form.get('allow_vote_changes') === 'on',
            closes_at: closes ? localInputToIso(String(closes)) : undefined,
            opens_at: opens ? localInputToIso(String(opens)) : undefined,
            remind_hours_before: Number(form.get('remind_hours_before') ?? 24),
            min_participation_pct: Number(form.get('min_participation_pct') || 0),
            low_participation_action: form.get('low_participation_action') as 'admin' | 'count',
            show_voter_names: form.get('show_voter_names') === 'on',
            max_runoffs: runoffs ? Number(runoffs) : undefined,
            prior_season_id: form.get('prior_season_id') ? Number(form.get('prior_season_id')) : undefined,
            min_prior_starts: Number(form.get('min_prior_starts') || 0),
          },
        })
        return error
      }}
    />
  )
}
