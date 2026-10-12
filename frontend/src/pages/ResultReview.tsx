import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'

type RoundDetail = components['schemas']['RoundDetail']
type LineOut = components['schemas']['LineOut']
type PenaltyKind = components['schemas']['PenaltyIn']['kind']
type Outcome = components['schemas']['DecisionIn']['outcome']

const PENALTY_KINDS: PenaltyKind[] = ['positions', 'points', 'dsq']

/** The state of the result, its version, and the protest deadline. */
export function ResultStatus({ round }: { round: RoundDetail }) {
  const { t, i18n } = useTranslation()
  if (!round.status) return null
  const deadline = round.protest_deadline
  const passed = !round.protest_window_open
  return (
    <p className="result-status">
      <span className={`state state-${round.status}`}>{t(`review.status.${round.status}`)}</span>
      <span className="muted">{t('review.statusLine', { version: round.version })}</span>
      {round.status === 'official' && round.approved_at ? (
        <span className="muted">
          {t('review.approvedAt', { date: formatDateTime(round.approved_at, i18n.language) })}
        </span>
      ) : (
        deadline && (
          <span className="muted">
            {t(passed ? 'review.deadlinePassed' : 'review.deadline', {
              date: formatDateTime(deadline, i18n.language),
            })}
          </span>
        )
      )}
    </p>
  )
}

export function ApproveButton({ round, onChange }: { round: RoundDetail; onChange: () => void }) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  if (!round.status || round.status === 'official') return null

  async function approve() {
    setError(null)
    const { error } = await api.POST('/api/rounds/{round_id}/result/approve', {
      params: { path: { round_id: round.id } },
    })
    if (error) setError(errorMessage(t, error))
    else onChange()
  }

  return (
    <div className="approve">
      <button type="button" onClick={approve}>
        {t('review.approve')}
      </button>
      <span className="muted">{t('review.approveHelp')}</span>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}

export function Versions({ round }: { round: RoundDetail }) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState<number | null>(null)
  const [lines, setLines] = useState<LineOut[]>([])
  if (round.versions.length < 2) return null

  async function toggle(number: number) {
    if (open === number) {
      setOpen(null)
      return
    }
    const { data } = await api.GET('/api/rounds/{round_id}/result/versions/{number}', {
      params: { path: { round_id: round.id, number } },
    })
    setLines(data ?? [])
    setOpen(number)
  }

  return (
    <>
      <h2>{t('review.versions')}</h2>
      <ol className="versions">
        {round.versions.map((version) => (
          <li key={version.number}>
            <strong>v{version.number}</strong> · {t(`review.versionKinds.${version.kind}`)} ·{' '}
            <span className="muted">
              {version.created_by} · {formatDateTime(version.created_at, i18n.language)}
            </span>
            {version.number === round.version && <span className="badge">{t('review.current')}</span>}
            {version.reason && <p className="reason">{version.reason}</p>}
            {version.number !== round.version && (
              <button type="button" className="secondary small" onClick={() => toggle(version.number)}>
                {open === version.number ? t('review.hide') : t('review.show')}
              </button>
            )}
            {open === version.number && (
              <ol className="old-lines">
                {lines.map((line) => (
                  <li key={line.entry_id}>
                    {line.position ?? t(`round.short.${line.status}`)} · {line.driver_name} ·{' '}
                    {t('audit.pts', { count: line.points })}
                  </li>
                ))}
              </ol>
            )}
          </li>
        ))}
      </ol>
    </>
  )
}

export function Penalties({
  round,
  adminView,
  onChange,
}: {
  round: RoundDetail
  adminView: boolean
  onChange: () => void
}) {
  const { t } = useTranslation()
  if (!round.status) return null
  return (
    <>
      <h2>{t('review.penalties')}</h2>
      {round.penalties.length === 0 ? (
        <p>{t('review.noPenalties')}</p>
      ) : (
        <ul className="list">
          {round.penalties.map((penalty) => (
            <li key={penalty.id}>
              <strong>{penalty.driver_name}</strong>:{' '}
              {t(`review.penaltyText.${penalty.kind}`, { value: penalty.value })} — {penalty.reason}
              <span className="muted">
                {' '}
                ({penalty.attempt && t('review.attemptN', { number: penalty.attempt })}
                {penalty.protest_id && `, ${t('review.fromProtest', { id: penalty.protest_id })}`})
              </span>
            </li>
          ))}
        </ul>
      )}
      {adminView && (
        <div className="forms">
          <ActionForm
            title={t('review.addPenalty')}
            submitLabel={t('review.addPenalty')}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/rounds/{round_id}/penalties', {
                params: { path: { round_id: round.id } },
                body: {
                  entry_id: Number(form.get('entry_id')),
                  kind: form.get('kind') as PenaltyKind,
                  value: Number(form.get('value') || 0),
                  reason: String(form.get('reason') ?? ''),
                },
              })
              if (!error) onChange()
              return error
            }}
          >
            <PenaltyFields round={round} />
            <label>
              {t('review.reason')}
              <input name="reason" required maxLength={500} />
            </label>
          </ActionForm>
        </div>
      )}
    </>
  )
}

function PenaltyFields({ round }: { round: RoundDetail }) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<PenaltyKind>('positions')
  return (
    <>
      <label>
        {t('review.penaltyDriver')}
        <select name="entry_id" required defaultValue="">
          <option value="" disabled>
            {t('common.select')}
          </option>
          {round.entries.map((entry) => (
            <option key={entry.entry_id} value={entry.entry_id}>
              {entry.driver_name}
            </option>
          ))}
        </select>
      </label>
      <div className="field-row">
        <label>
          {t('review.kind')}
          <select name="kind" value={kind} onChange={(event) => setKind(event.target.value as PenaltyKind)}>
            {PENALTY_KINDS.map((option) => (
              <option key={option} value={option}>
                {t(`review.penaltyKinds.${option}`)}
              </option>
            ))}
          </select>
        </label>
        {kind !== 'dsq' && (
          <label>
            {t('review.value')}
            <input name="value" type="number" min={1} required />
          </label>
        )}
      </div>
    </>
  )
}

export function Protests({
  round,
  adminView,
  onChange,
}: {
  round: RoundDetail
  adminView: boolean
  onChange: () => void
}) {
  const { t, i18n } = useTranslation()
  if (!round.status) return null
  return (
    <>
      <h2>{t('review.protests')}</h2>
      {round.protests.length === 0 ? (
        <p>{t('review.noProtests')}</p>
      ) : (
        <ul className="protests">
          {round.protests.map((protest) => (
            <li key={protest.id} className="card">
              <div className="audit-head">
                <strong>#{protest.id}</strong>
                <span className={`badge protest-${protest.status}`}>
                  {t(`review.protestStatus.${protest.status}`)}
                </span>
                <span className="muted">
                  {t('review.by', { name: protest.submitted_by })} ·{' '}
                  {formatDateTime(protest.created_at, i18n.language)}
                  {protest.lap !== null && protest.lap !== undefined && ` · ${t('review.lap')} ${protest.lap}`}
                </span>
              </div>
              <p>{protest.description}</p>
              {protest.involved.length > 0 && (
                <p className="muted">
                  {t('review.involved')}: {protest.involved.join(', ')}
                </p>
              )}
              {protest.decision && (
                <p className="reason">
                  {protest.decided_by}: {protest.decision}
                </p>
              )}
              {adminView && protest.status === 'open' && (
                <DecisionForm protestId={protest.id} round={round} onChange={onChange} />
              )}
            </li>
          ))}
        </ul>
      )}
      {round.can_protest && (
        <div className="forms">
          <ActionForm
            title={t('review.newProtest')}
            submitLabel={t('review.send')}
            onSubmit={async (form) => {
              const lap = form.get('lap')
              const { error } = await api.POST('/api/rounds/{round_id}/protests', {
                params: { path: { round_id: round.id } },
                body: {
                  description: String(form.get('description') ?? ''),
                  entry_ids: form.getAll('entry_ids').map(Number),
                  lap: lap ? Number(lap) : null,
                },
              })
              if (!error) onChange()
              return error
            }}
          >
            <label>
              {t('review.description')}
              <textarea name="description" rows={3} required maxLength={2000} />
            </label>
            <fieldset className="checks">
              <legend>{t('review.involved')}</legend>
              {round.entries.map((entry) => (
                <label key={entry.entry_id} className="check">
                  <input type="checkbox" name="entry_ids" value={entry.entry_id} />
                  {entry.driver_name}
                </label>
              ))}
            </fieldset>
            <label>
              {t('review.lap')}
              <input name="lap" type="number" min={0} />
            </label>
          </ActionForm>
        </div>
      )}
    </>
  )
}

function DecisionForm({
  protestId,
  round,
  onChange,
}: {
  protestId: number
  round: RoundDetail
  onChange: () => void
}) {
  const { t } = useTranslation()
  const [outcome, setOutcome] = useState<Outcome>('dismissed')
  const [withPenalty, setWithPenalty] = useState(false)
  return (
    <ActionForm
      title={`${t('review.decide')} #${protestId}`}
      submitLabel={t('review.save')}
      onSubmit={async (form) => {
        const penalty =
          outcome === 'upheld' && withPenalty
            ? {
                entry_id: Number(form.get('entry_id')),
                kind: form.get('kind') as PenaltyKind,
                value: Number(form.get('value') || 0),
              }
            : null
        const { error } = await api.POST('/api/protests/{protest_id}/decision', {
          params: { path: { protest_id: protestId } },
          body: { outcome, decision: String(form.get('decision') ?? ''), penalty },
        })
        if (!error) onChange()
        return error
      }}
    >
      <label>
        {t('review.outcome')}
        <select value={outcome} onChange={(event) => setOutcome(event.target.value as Outcome)}>
          <option value="dismissed">{t('review.protestStatus.dismissed')}</option>
          <option value="upheld">{t('review.protestStatus.upheld')}</option>
        </select>
      </label>
      <label>
        {t('review.decision')}
        <textarea name="decision" rows={2} required maxLength={2000} />
      </label>
      {outcome === 'upheld' && (
        <label className="check">
          <input type="checkbox" checked={withPenalty} onChange={(event) => setWithPenalty(event.target.checked)} />
          {t('review.addPenaltyToo')}
        </label>
      )}
      {outcome === 'upheld' && withPenalty && <PenaltyFields round={round} />}
    </ActionForm>
  )
}
