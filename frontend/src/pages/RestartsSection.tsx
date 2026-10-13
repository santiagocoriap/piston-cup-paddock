import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { useLoad } from '../lib/useLoad'

type Entry = components['schemas']['EntryOption']
type RestartOut = components['schemas']['RestartOut']
type RestartIn = components['schemas']['RestartIn']
type ResponsibilityIn = components['schemas']['ResponsibilityIn']

const REASONS: RestartIn['reason'][] = [
  'first_lap_crash',
  'technical_issue',
  'server_problem',
  'wrong_configuration',
  'false_start',
  'other',
]
const RESPONSIBILITIES: NonNullable<RestartIn['responsibility']>[] = [
  'drivers',
  'racing_incident',
  'technical',
  'unknown',
]
const REVIEWS: NonNullable<RestartIn['review_status']>[] = ['pending', 'confirmed', 'disputed']

function optionalNumber(value: FormDataEntryValue | null): number | null {
  return value === null || value === '' ? null : Number(value)
}

export function RestartsSection({
  roundId,
  entries,
  adminView,
  refresh = 0,
}: {
  roundId: number
  entries: Entry[]
  adminView: boolean
  /** Change this number to load the restarts again. */
  refresh?: number
}) {
  const { t } = useTranslation()
  const path = { round_id: roundId }
  const data = useLoad(() => api.GET('/api/rounds/{round_id}/restarts', { params: { path } }), [roundId, refresh])

  if (!data.data) return null
  const { attempts, restarts, summary } = data.data
  return (
    <>
      <h2>{t('restarts.title')}</h2>
      {summary.total === 0 ? (
        <p>{t('restarts.none')}</p>
      ) : (
        <p>
          <strong>{t('restarts.count', { count: summary.total })}</strong>
        </p>
      )}
      {attempts.length > 0 && (
        <ol className="attempts">
          {attempts.map((attempt) => (
            <li key={attempt.number} className={`attempt ${attempt.status}`}>
              {t('restarts.attempt', { number: attempt.number })}:{' '}
              {t(`restarts.attemptStatus.${attempt.status}`)}
            </li>
          ))}
        </ol>
      )}

      {restarts.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('restarts.startsColumn')}</th>
                <th scope="col">{t('restarts.lap')}</th>
                <th scope="col">{t('restarts.reason')}</th>
                <th scope="col">{t('restarts.location')}</th>
                <th scope="col">{t('restarts.responsibility')}</th>
                <th scope="col">{t('restarts.review')}</th>
                <th scope="col">{t('restarts.requestedBy')}</th>
              </tr>
            </thead>
            <tbody>
              {restarts.map((restart) => (
                <RestartRow
                  key={restart.id}
                  restart={restart}
                  entries={entries}
                  adminView={adminView}
                  onSaved={data.reload}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {summary.total > 0 && (
        <div className="card summary">
          <h3>{t('restarts.caused')}</h3>
          {summary.caused.length === 0 ? (
            <p>{t('restarts.noCaused')}</p>
          ) : (
            <ul className="list">
              {summary.caused.map((row) => (
                <li key={row.entry_id}>
                  {row.driver_name}: <strong>{row.total}</strong>
                  {row.shared > 0 && (
                    <span className="badge">{t('restarts.shared', { count: row.shared })}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {summary.caused.some((row) => row.shared > 0) && (
            <p className="muted">{t('restarts.sharedNote')}</p>
          )}
          <p className="muted">
            {t('restarts.others', {
              pending: summary.pending_or_disputed,
              incident: summary.racing_incident,
              technical: summary.technical,
              unknown: summary.unknown,
            })}
          </p>
        </div>
      )}

      {adminView && (
        <div className="forms">
          <ActionForm
            title={t('restarts.record')}
            submitLabel={t('restarts.record')}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/rounds/{round_id}/restarts', {
                params: { path },
                body: {
                  lap: optionalNumber(form.get('lap')),
                  elapsed_seconds: optionalNumber(form.get('elapsed_seconds')),
                  location: String(form.get('location') ?? ''),
                  reason: form.get('reason') as RestartIn['reason'],
                  explanation: String(form.get('explanation') ?? ''),
                  requested_by_id: optionalNumber(form.get('requested_by_id')),
                  executed_by_id: optionalNumber(form.get('executed_by_id')),
                  responsibility: form.get('responsibility') as RestartIn['responsibility'],
                  driver_entry_ids: form.getAll('driver_entry_ids').map(Number),
                  review_status: form.get('review_status') as RestartIn['review_status'],
                },
              })
              if (!error) data.reload()
              return error
            }}
          >
            <div className="field-row">
              <label>
                {t('restarts.lap')}
                <input name="lap" type="number" min={0} />
              </label>
              <label>
                {t('restarts.elapsed')}
                <input name="elapsed_seconds" type="number" min={0} />
              </label>
            </div>
            <label>
              {t('restarts.location')}
              <input name="location" maxLength={200} />
            </label>
            <label>
              {t('restarts.reason')}
              <select name="reason" defaultValue="first_lap_crash">
                {REASONS.map((reason) => (
                  <option key={reason} value={reason}>
                    {t(`restarts.reasons.${reason}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('restarts.explanation')}
              <textarea name="explanation" rows={2} maxLength={2000} />
            </label>
            <div className="field-row">
              <DriverSelect name="requested_by_id" label={t('restarts.requestedBy')} entries={entries} />
              <DriverSelect name="executed_by_id" label={t('restarts.executedBy')} entries={entries} />
            </div>
            <ResponsibilityFields entries={entries} />
          </ActionForm>
        </div>
      )}
    </>
  )
}

function DriverSelect({ name, label, entries }: { name: string; label: string; entries: Entry[] }) {
  const { t } = useTranslation()
  return (
    <label>
      {label}
      <select name={name} defaultValue="">
        <option value="">{t('restarts.nobody')}</option>
        {entries.map((entry) => (
          <option key={entry.entry_id} value={entry.driver_id}>
            {entry.driver_name}
          </option>
        ))}
      </select>
    </label>
  )
}

function ResponsibilityFields({
  entries,
  initial,
}: {
  entries: Entry[]
  initial?: Pick<RestartOut, 'responsibility' | 'review_status' | 'responsible'>
}) {
  const { t } = useTranslation()
  const [responsibility, setResponsibility] = useState(initial?.responsibility ?? 'unknown')
  const chosen = new Set(initial?.responsible.map((r) => r.entry_id))
  return (
    <>
      <label>
        {t('restarts.responsibility')}
        <select
          name="responsibility"
          value={responsibility}
          onChange={(event) => setResponsibility(event.target.value)}
        >
          {RESPONSIBILITIES.map((option) => (
            <option key={option} value={option}>
              {t(`restarts.responsibilities.${option}`)}
            </option>
          ))}
        </select>
      </label>
      {responsibility === 'drivers' && (
        <fieldset className="checks">
          <legend>{t('restarts.responsibleDrivers')}</legend>
          {entries.map((entry) => (
            <label key={entry.entry_id} className="check">
              <input
                type="checkbox"
                name="driver_entry_ids"
                value={entry.entry_id}
                defaultChecked={chosen.has(entry.entry_id)}
              />
              {entry.driver_name}
            </label>
          ))}
        </fieldset>
      )}
      <label>
        {t('restarts.review')}
        <select name="review_status" defaultValue={initial?.review_status ?? 'pending'}>
          {REVIEWS.map((option) => (
            <option key={option} value={option}>
              {t(`restarts.reviews.${option}`)}
            </option>
          ))}
        </select>
      </label>
    </>
  )
}

function RestartRow({
  restart,
  entries,
  adminView,
  onSaved,
}: {
  restart: RestartOut
  entries: Entry[]
  adminView: boolean
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const names = restart.responsible.map((r) => r.driver_name).join(', ')
  return (
    <>
      <tr>
        <td>
          {restart.abandoned_attempt} → {restart.replacement_attempt ?? '—'}
        </td>
        <td>{restart.lap ?? '—'}</td>
        <td title={restart.explanation || undefined}>{t(`restarts.reasons.${restart.reason}`)}</td>
        <td>{restart.location || '—'}</td>
        <td>
          {restart.responsibility === 'drivers' ? names : t(`restarts.responsibilities.${restart.responsibility}`)}
          {restart.responsible.length > 1 && <span className="badge">{t('restarts.sharedBadge')}</span>}
          {restart.suggested && restart.suggested.length > 0 && restart.review_status === 'pending' && (
            <div className="muted">
              {t('restarts.suggested', { names: restart.suggested.map((s) => s.driver_name).join(', ') })}
            </div>
          )}
          {restart.incidents && restart.incidents.length > 0 && (
            <details>
              <summary>{t('restarts.incidents', { count: restart.incidents.length })}</summary>
              <ul>
                {restart.incidents.map((incident) => (
                  <li key={incident.key}>
                    {t('restarts.incidentLine', {
                      seconds: incident.seconds,
                      lap: incident.lap ?? '—',
                      cars: incident.cars.join(' + '),
                    })}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </td>
        <td>
          <span className={`badge review-${restart.review_status}`}>
            {t(`restarts.reviews.${restart.review_status}`)}
          </span>
        </td>
        <td>
          {restart.requested_by ?? '—'}
          {adminView && (
            <button type="button" className="secondary small" onClick={() => setEditing(!editing)}>
              {t('restarts.edit')}
            </button>
          )}
        </td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={7}>
            <ActionForm
              title={`${t('restarts.edit')} · ${t('restarts.attempt', { number: restart.abandoned_attempt })}`}
              submitLabel={t('restarts.save')}
              onSubmit={async (form) => {
                const { error } = await api.PUT('/api/restarts/{restart_id}/responsibility', {
                  params: { path: { restart_id: restart.id } },
                  body: {
                    responsibility: form.get('responsibility') as ResponsibilityIn['responsibility'],
                    driver_entry_ids: form.getAll('driver_entry_ids').map(Number),
                    review_status: form.get('review_status') as ResponsibilityIn['review_status'],
                    reason: String(form.get('reason') ?? ''),
                  },
                })
                if (!error) {
                  setEditing(false)
                  onSaved()
                }
                return error
              }}
            >
              <ResponsibilityFields entries={entries} initial={restart} />
              <label>
                {t('restarts.changeReason')}
                <input name="reason" maxLength={500} />
              </label>
            </ActionForm>
          </td>
        </tr>
      )}
    </>
  )
}
