import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime, formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type FlaggedLap = components['schemas']['FlaggedLapOut']
type SessionType = 'race' | 'qualifying' | 'practice'

/** The laps of the Paddock script that failed a check. The app keeps them, and an admin checks
 * them again (for example after a new Steam ID), counts them for a round, or deletes them. */
export function FlaggedLapsCard({ championshipId }: { championshipId: number }) {
  const { t } = useTranslation()
  const laps = useLoad(
    () => api.GET('/api/championships/{championship_id}/telemetry/flagged', { params: { path: { championship_id: championshipId } } }),
    [championshipId],
  )
  const rows = laps.data ?? []
  if (rows.length === 0) return null
  return (
    <div className="card" role="region" aria-label={t('flaggedLaps.title')}>
      <h3>{t('flaggedLaps.title')}</h3>
      <p className="muted">{t('flaggedLaps.help')}</p>
      <RecheckAll championshipId={championshipId} onDone={laps.reload} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('flaggedLaps.driver')}</th>
              <th scope="col">{t('flaggedLaps.lap')}</th>
              <th scope="col">{t('flaggedLaps.issue')}</th>
              <th scope="col">{t('flaggedLaps.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((lap) => (
              <FlaggedRow key={lap.id} lap={lap} onChange={laps.reload} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

type Hint = { server_laps?: number; seconds?: number; lap_ms?: number }

/** The nearest server lap of the driver, so an admin sees why the lap did not count. */
function hintText(t: TFunction, raw: Record<string, unknown>): string {
  const hint = raw as Hint
  if (!hint.server_laps) return t('flaggedLaps.hintNone')
  const seconds = hint.seconds ?? 0
  return t('flaggedLaps.hint', {
    time: `${seconds > 0 ? '+' : '−'}${Math.floor(Math.abs(seconds) / 60)}:${String(Math.abs(seconds) % 60).padStart(2, '0')}`,
    diff: `${(hint.lap_ms ?? 0) > 0 ? '+' : ''}${((hint.lap_ms ?? 0) / 1000).toFixed(3)}`,
  })
}

function RecheckAll({ championshipId, onDone }: { championshipId: number; onDone: () => void }) {
  const { t } = useTranslation()
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function run() {
    setBusy(true)
    setMessage(null)
    const { data, error } = await api.POST('/api/championships/{championship_id}/telemetry/flagged/recheck', {
      params: { path: { championship_id: championshipId } },
    })
    setBusy(false)
    if (error || !data) return setMessage(errorMessage(t, error))
    setMessage(t('flaggedLaps.recheckedAll', { league: data.league, still: data.rejected + data.pending }))
    onDone()
  }
  return (
    <div className="flagged-actions">
      <button type="button" className="secondary" disabled={busy} onClick={run}>
        {busy ? t('flaggedLaps.recheckingAll') : t('flaggedLaps.recheckAll')}
      </button>
      {message && <span role="status">{message}</span>}
    </div>
  )
}

function FlaggedRow({ lap, onChange }: { lap: FlaggedLap; onChange: () => void }) {
  const { t, i18n } = useTranslation()
  const [session, setSession] = useState<SessionType>('race')
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<{ error?: unknown; data?: { state: string; issues: string[] } }>) {
    setMessage(null)
    const { error, data } = await action()
    if (error) return setMessage(errorMessage(t, error))
    if (data && data.state === 'rejected') return setMessage(t('flaggedLaps.still', { issue: issueText(data.issues) }))
    onChange()
  }

  function issueText(issues: string[]) {
    return issues.map((issue) => t(`flaggedLaps.issues.${issue}`, { defaultValue: issue })).join(', ')
  }

  const path = { lap_id: lap.id }
  return (
    <tr>
      <td>
        {lap.driver_name ?? <span className="mono">{lap.steam_guid}</span>}
      </td>
      <td>
        <span className="mono">{formatLapTime(lap.lap_time_ms)}</span>
        <span className="muted extra-guid">
          {lap.round_number ? t('flaggedLaps.round', { number: lap.round_number }) + ' · ' : ''}
          {formatDateTime(lap.recorded_at, i18n.language)}
        </span>
      </td>
      <td>
        {issueText(lap.issues)}
        {lap.match_hint && <span className="muted extra-guid">{hintText(t, lap.match_hint)}</span>}
        {message && (
          <p role="alert" className="error">
            {message}
          </p>
        )}
      </td>
      <td>
        <div className="flagged-actions">
          <button type="button" className="secondary small" onClick={() => run(() => api.POST('/api/telemetry-laps/{lap_id}/recheck', { params: { path } }))}>
            {t('flaggedLaps.recheck')}
          </button>
          {lap.round_id && lap.driver_id && !lap.issues.includes('bad_samples') && !lap.issues.includes('partial_samples') && (
            <>
              <select value={session} onChange={(event) => setSession(event.target.value as SessionType)} aria-label={t('flaggedLaps.session')}>
                <option value="race">{t('flaggedLaps.sessions.race')}</option>
                <option value="qualifying">{t('flaggedLaps.sessions.qualifying')}</option>
                <option value="practice">{t('flaggedLaps.sessions.practice')}</option>
              </select>
              <button
                type="button"
                className="secondary small"
                onClick={() =>
                  run(() => api.POST('/api/telemetry-laps/{lap_id}/accept', { params: { path }, body: { round_id: lap.round_id!, session_type: session } }))
                }
              >
                {t('flaggedLaps.accept')}
              </button>
            </>
          )}
          <button
            type="button"
            className="link"
            onClick={() => {
              if (window.confirm(t('flaggedLaps.confirmDelete'))) run(() => api.DELETE('/api/telemetry-laps/{lap_id}', { params: { path } }))
            }}
          >
            {t('flaggedLaps.delete')}
          </button>
        </div>
      </td>
    </tr>
  )
}
