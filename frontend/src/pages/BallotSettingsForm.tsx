import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { isoToLocalInput, localInputToIso } from '../lib/format'

type Ballot = components['schemas']['BallotDetail']
type Settings = components['schemas']['BallotSettingsIn']

/** The settings of a draft ballot. The fields show the current values. */
export function BallotSettingsForm({ ballot, onDone }: { ballot: Ballot; onDone: () => void }) {
  const { t } = useTranslation()
  const [method, setMethod] = useState(ballot.method as 'multiple' | 'single')
  const date = (iso: string | null | undefined) => (iso ? isoToLocalInput(iso) : '')
  return (
    <ActionForm
      title={t('voting.settings')}
      submitLabel={t('common.save')}
      onDone={onDone}
      onSubmit={async (form) => {
        const text = (name: string) => String(form.get(name) ?? '')
        const opens = text('opens_at')
        const closes = text('closes_at')
        const runoffs = text('max_runoffs')
        const body: Settings = {
          title: text('title'),
          method,
          selection_limit: method === 'multiple' ? Number(text('selection_limit') || 1) : 1,
          totals_visibility: text('totals_visibility') as Settings['totals_visibility'],
          choice_visibility: text('choice_visibility') as Settings['choice_visibility'],
          allow_vote_changes: form.get('allow_vote_changes') === 'on',
          show_voter_names: form.get('show_voter_names') === 'on',
          remind_hours_before: Number(text('remind_hours_before') || 0),
          min_participation_pct: Number(text('min_participation_pct') || 0),
          low_participation_action: text('low_participation_action') as 'admin' | 'count',
        }
        if (ballot.kind === 'car_class') body.slots = Number(text('slots') || 1)
        if (opens) body.opens_at = localInputToIso(opens)
        if (closes) body.closes_at = localInputToIso(closes)
        if (runoffs) body.max_runoffs = Number(runoffs)
        const { error } = await api.PATCH('/api/ballots/{ballot_id}', {
          params: { path: { ballot_id: ballot.id } },
          body,
        })
        return error
      }}
    >
      <label>
        {t('voting.titleLabel')}
        <input name="title" required maxLength={150} defaultValue={ballot.title} />
      </label>
      <div className="field-row">
        <label>
          {t('voting.methodLabel')}
          <select value={method} onChange={(event) => setMethod(event.target.value as 'multiple' | 'single')}>
            <option value="multiple">{t('voting.multipleShort')}</option>
            <option value="single">{t('voting.method.single')}</option>
          </select>
        </label>
        {method === 'multiple' && (
          <label>
            {t('voting.limit')}
            <input name="selection_limit" type="number" min={1} max={50} defaultValue={ballot.selection_limit} required />
          </label>
        )}
        {ballot.kind === 'car_class' && (
          <label>
            {t('voting.slots')}
            <input name="slots" type="number" min={1} max={10} defaultValue={ballot.slots} required />
          </label>
        )}
      </div>
      <div className="field-row">
        <label>
          {t('voting.totalsLabel')}
          <select name="totals_visibility" defaultValue={ballot.totals_visibility}>
            {(['live', 'after_close', 'hidden'] as const).map((value) => (
              <option key={value} value={value}>
                {t(`voting.totals.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('voting.choicesLabel')}
          <select name="choice_visibility" defaultValue={ballot.choice_visibility}>
            {(['hidden', 'visible'] as const).map((value) => (
              <option key={value} value={value}>
                {t(`voting.choices.${value}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="field-row">
        <label>
          {t('voting.opensLabel')}
          <input name="opens_at" type="datetime-local" defaultValue={date(ballot.opens_at)} />
        </label>
        <label>
          {t('voting.closesLabel')}
          <input name="closes_at" type="datetime-local" defaultValue={date(ballot.closes_at)} />
        </label>
        <label>
          {t('voting.remindHours')}
          <input name="remind_hours_before" type="number" min={0} max={168} defaultValue={ballot.remind_hours_before} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" name="show_voter_names" defaultChecked={ballot.show_voter_names} />
        {t('voting.showVoterNames')}
      </label>
      <label className="check">
        <input type="checkbox" name="allow_vote_changes" defaultChecked={ballot.allow_vote_changes} />
        {t('voting.allowChanges')}
      </label>
      <details>
        <summary>{t('voting.steps.advanced')}</summary>
        <div className="field-row">
          <label>
            {t('voting.minParticipation')}
            <input
              name="min_participation_pct"
              type="number"
              min={0}
              max={100}
              defaultValue={ballot.min_participation_pct}
            />
          </label>
          <label>
            {t('voting.lowParticipation')}
            <select name="low_participation_action" defaultValue={ballot.low_participation_action}>
              <option value="admin">{t('voting.lowActions.admin')}</option>
              <option value="count">{t('voting.lowActions.count')}</option>
            </select>
          </label>
          <label>
            {t('voting.maxRunoffs')}
            <input name="max_runoffs" type="number" min={0} max={20} defaultValue={ballot.max_runoffs ?? ''} />
          </label>
        </div>
      </details>
    </ActionForm>
  )
}
