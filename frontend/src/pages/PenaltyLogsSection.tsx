import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, readCookie } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Logs = components['schemas']['PenaltyLogsOut']

const SELECTABLE = new Set(['served', 'time', 'dsq'])

/** Upload the Real Penalty logs of a race night, check what they add, and apply them. */
export function PenaltyLogsSection({ roundId, onApplied }: { roundId: number; onApplied: () => void }) {
  const { t } = useTranslation()
  const path = { round_id: roundId }
  const logs = useLoad(() => api.GET('/api/rounds/{round_id}/penalty-logs', { params: { path } }), [roundId])
  const [override, setOverride] = useState<Logs | null>(null)
  const [message, setMessage] = useState<{ kind: 'error' | 'status'; text: string } | null>(null)
  const data = override ?? logs.data

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage(null)
    // A file upload goes with a plain fetch. The typed client sends JSON.
    const response = await fetch(`/api/rounds/${roundId}/penalty-logs`, {
      method: 'POST',
      body: new FormData(event.currentTarget),
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
    }).catch(() => null)
    const body = response ? await response.json().catch(() => null) : null
    if (!response?.ok) {
      setMessage({ kind: 'error', text: errorMessage(t, body) })
      return
    }
    setOverride(body as Logs)
    if ((body as Logs).new_files === 0) setMessage({ kind: 'status', text: t('penaltyLogs.sameFiles') })
  }

  return (
    <div className="card import">
      <h3>{t('penaltyLogs.title')}</h3>
      <p className="muted">{t('penaltyLogs.help')}</p>
      <form className="upload" onSubmit={upload} aria-label={t('penaltyLogs.title')}>
        <label>
          {t('penaltyLogs.files')}
          <input name="files" type="file" accept=".log,text/plain" multiple required />
        </label>
        <button type="submit">{t('penaltyLogs.upload')}</button>
      </form>
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'muted'}>
          {message.text}
        </p>
      )}
      {data && data.logs > 0 && (
        <LogsPreview
          key={`${data.logs}-${data.penalties.map((p) => p.key).join()}`}
          roundId={roundId}
          data={data}
          onApplied={(next) => {
            setOverride(next)
            onApplied()
          }}
        />
      )}
    </div>
  )
}

function LogsPreview({
  roundId,
  data,
  onApplied,
}: {
  roundId: number
  data: Logs
  onApplied: (next: Logs) => void
}) {
  const { t } = useTranslation()
  const selectable = data.penalties.filter((p) => SELECTABLE.has(p.kind) && !p.already && p.entry_id !== null)
  const [chosen, setChosen] = useState<string[]>(() => selectable.map((p) => p.key))
  const [error, setError] = useState<string | null>(null)
  const [applied, setApplied] = useState(false)
  const newStarts = data.starts.filter((start) => start.new).length

  async function apply() {
    setError(null)
    const { data: next, error } = await api.POST('/api/rounds/{round_id}/penalty-logs/apply', {
      params: { path: { round_id: roundId } },
      body: { penalty_keys: chosen },
    })
    if (error || !next) setError(errorMessage(t, error))
    else {
      setApplied(true)
      onApplied(next)
    }
  }

  return (
    <section className="preview" aria-label={t('penaltyLogs.title')}>
      {data.final_log && <p>{t('penaltyLogs.final', { file: data.final_log })}</p>}
      {data.warnings.map((warning) => (
        <p key={warning} className="warning">
          {t(`penaltyLogs.warnings.${warning}`)}
        </p>
      ))}
      <p>
        {t('penaltyLogs.starts', { count: data.starts.length })} ·{' '}
        {t('penaltyLogs.existing', { count: data.existing_restarts })}
      </p>
      <p>
        <strong>
          {newStarts > 0 ? t('penaltyLogs.newStarts', { count: newStarts }) : t('penaltyLogs.noNewStarts')}
        </strong>
      </p>

      <h5>{t('penaltyLogs.penalties')}</h5>
      {data.penalties.length === 0 ? (
        <p className="muted">{t('penaltyLogs.noPenalties')}</p>
      ) : (
        <ul className="list">
          {data.penalties.map((penalty) => {
            const canChoose = SELECTABLE.has(penalty.kind) && !penalty.already && penalty.entry_id !== null
            return (
              <li key={penalty.key}>
                <label className="check">
                  <input
                    type="checkbox"
                    disabled={!canChoose}
                    checked={chosen.includes(penalty.key)}
                    onChange={(event) =>
                      setChosen((list) =>
                        event.target.checked ? [...list, penalty.key] : list.filter((key) => key !== penalty.key),
                      )
                    }
                  />
                  <strong>{penalty.driver_name ?? penalty.name}</strong>: {t(`penaltyLogs.kind.${penalty.kind}`)}
                  {penalty.penalty && ` · ${penalty.penalty}`}
                  {penalty.kind === 'time' && ` · ${t('penaltyLogs.seconds', { count: penalty.seconds })}`}
                  {penalty.already && <span className="badge">{t('penaltyLogs.already')}</span>}
                </label>
              </li>
            )
          })}
        </ul>
      )}
      {data.penalties.some((p) => p.kind === 'time') && <p className="warning">{t('penaltyLogs.timeHint')}</p>}
      {data.ignored_penalties > 0 && (
        <p className="muted">{t('penaltyLogs.ignored', { count: data.ignored_penalties })}</p>
      )}

      {data.invalid_laps.length > 0 && (
        <>
          <h5>{t('penaltyLogs.invalidLaps')}</h5>
          <ul className="list">
            {data.invalid_laps.map((lap) => (
              <li key={`${lap.guid}-${lap.lap_time_ms}`}>
                {lap.name} · {formatLapTime(lap.lap_time_ms)} ·{' '}
                {lap.lap_id ? t('penaltyLogs.lapFound') : t('penaltyLogs.lapMissing')}
              </li>
            ))}
          </ul>
        </>
      )}

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {applied ? (
        <p role="status" className="success">
          {t('penaltyLogs.applied')}
        </p>
      ) : (
        <button type="button" onClick={apply}>
          {t('penaltyLogs.apply')}
        </button>
      )}
    </section>
  )
}
