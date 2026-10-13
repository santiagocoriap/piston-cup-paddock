import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Loading } from '../components/Layout'
import { errorMessage } from '../lib/errors'
import { formatDateTime, formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useAdminView } from '../session'
import { penaltyChanged } from '../lib/results'
import { ImportSection } from './ImportSection'
import { EngineerSection } from './EngineerSection'
import { IncidentsSection } from './IncidentsSection'
import { LapsSection } from './LapsSection'
import { PenaltyLogsSection } from './PenaltyLogsSection'
import { ReplaySection } from './ReplaySection'
import { ReportSection } from './ReportSection'
import { Briefing } from './Briefing'
import { RestartsSection } from './RestartsSection'
import { ApproveButton, Penalties, Protests, ResultStatus, Versions } from './ResultReview'
import { TelemetrySection } from './TelemetrySection'

type RoundDetail = components['schemas']['RoundDetail']
type Status = components['schemas']['LineIn']['status']
type Row = { status: Status | 'absent'; position: string; pole: boolean; fastest_lap: boolean }

const STATUSES: (Status | 'absent')[] = ['absent', 'finished', 'dnf', 'dns', 'dsq']

export function RoundPage() {
  const { t, i18n } = useTranslation()
  const roundId = Number(useParams().roundId)
  const round = useLoad(
    () => api.GET('/api/rounds/{round_id}', { params: { path: { round_id: roundId } } }),
    [roundId],
  )

  // A saved result accepts the current start, so the restarts section loads again.
  const [saves, setSaves] = useState(0)
  // An applied file changes the entered result, so the result form starts again from it.
  const [imports, setImports] = useState(0)
  const data = round.data
  // A steward or a custom role gets only the tools of its capabilities.
  const staffView = useAdminView((data?.capabilities.length ?? 0) > 0)
  if (!data) return <Loading failed={round.failed} />
  const may = (capability: string) => staffView && data.capabilities.includes(capability)
  const rules = data.rules
  const hasIncidents = data.result?.some((line) => line.incidents !== null && line.incidents !== undefined) ?? false
  const timeOrGap = (line: NonNullable<typeof data.result>[number]) => {
    if (line.laps_down) return t('round.lapsDown', { count: line.laps_down })
    if (line.gap_ms !== null && line.gap_ms !== undefined) return `+${(line.gap_ms / 1000).toFixed(3)}`
    return formatLapTime(line.total_ms)
  }
  const changed = () => {
    round.reload()
    setSaves((n) => n + 1)
  }
  return (
    <section>
      <p className="muted">
        {data.championship_name} · <Link to={`/seasons/${data.season_id}`}>{data.season_name}</Link>
      </p>
      <h1>
        {t('round.title', { number: data.number })}: {data.track_name} · {data.layout_name}
      </h1>
      <p className="muted">{formatDateTime(data.scheduled_at, i18n.language)}</p>

      <Briefing round={data} />

      <h2>{t('round.result')}</h2>
      <ResultStatus round={data} />
      {data.handicap_checks.length > 0 && (
        <div className="card warning" role="status">
          <strong>{t('round.handicapChecks')}</strong>
          <ul>
            {data.handicap_checks.map((c) => (
              <li key={c.entry_id}>
                {t('round.handicapCheck', {
                  name: c.driver_name,
                  assignedKg: c.assigned_kg,
                  assignedPct: c.assigned_pct,
                  observedKg: c.observed_kg,
                  observedPct: c.observed_pct,
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
      {may('results') && <ApproveButton round={data} onChange={changed} />}
      {data.result === null || data.result === undefined ? (
        <p>{t('round.noResult')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('round.position')}</th>
                <th scope="col">#</th>
                <th scope="col">{t('season.driver')}</th>
                <th scope="col">{t('round.laps')}</th>
                <th scope="col">{t('round.timeGap')}</th>
                {hasIncidents && <th scope="col">{t('round.incidents')}</th>}
                <th scope="col">{t('round.points')}</th>
              </tr>
            </thead>
            <tbody>
              {data.result.map((line) => (
                <tr key={line.entry_id}>
                  <td>{line.position ?? t(`round.short.${line.status}`)}</td>
                  <td>{line.number}</td>
                  <td>
                    <Link to={`/drivers/${line.driver_id}`}>{line.driver_name}</Link>
                    {line.status === 'dnf' && <span className="badge">DNF</span>}
                    {penaltyChanged(line) && (
                      <span
                        className="badge penalty"
                        title={t('review.entered', {
                          value: line.entered_position ?? t(`round.short.${line.entered_status}`),
                        })}
                      >
                        {t('review.penaltyMark')}
                      </span>
                    )}
                    {line.pole && rules.pole_bonus > 0 && <span className="badge">{t('round.pole')}</span>}
                    {line.fastest_lap && rules.fastest_lap_bonus > 0 && (
                      <span className="badge">{t('round.fastestLap')}</span>
                    )}
                  </td>
                  <td>{line.laps ?? '—'}</td>
                  <td>{timeOrGap(line)}</td>
                  {hasIncidents && <td>{line.incidents ?? '—'}</td>}
                  <td>{line.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted">
        {t('round.rules', { version: rules.version, points: rules.points_by_position.join('-') })}{' '}
        {(rules.pole_bonus > 0 || rules.fastest_lap_bonus > 0) &&
          t('round.bonuses', { pole: rules.pole_bonus, fastest: rules.fastest_lap_bonus })}
      </p>

      {may('results') && (
        <ImportSection
          roundId={data.id}
          entries={data.entries}
          onApplied={() => {
            changed()
            setImports((n) => n + 1)
          }}
        />
      )}
      {may('results') && <PenaltyLogsSection roundId={data.id} onApplied={changed} />}
      {may('results') && <ResultForm key={imports} round={data} onSaved={changed} />}

      <LapsSection key={`${imports}-${saves}`} roundId={data.id} />
      <IncidentsSection roundId={data.id} />
      <ReplaySection roundId={data.id} />

      <Penalties round={data} adminView={may('penalties')} onChange={changed} />
      <Protests round={data} adminView={may('penalties')} onChange={changed} />
      <Versions round={data} />

      <RestartsSection roundId={data.id} entries={data.entries} adminView={may('restarts')} refresh={saves} />

      <TelemetrySection roundId={data.id} />
      <EngineerSection roundId={data.id} />

      <ReportSection target={{ kind: 'round', id: data.id }} adminView={may('reports')} />
    </section>
  )
}

function initialRows(round: RoundDetail): Record<number, Row> {
  const rows: Record<number, Row> = {}
  for (const entry of round.entries) {
    const line = round.result?.find((l) => l.entry_id === entry.entry_id)
    rows[entry.entry_id] = line
      ? {
          status: line.entered_status,
          position: line.entered_position ? String(line.entered_position) : '',
          pole: line.pole ?? false,
          fastest_lap: line.fastest_lap ?? false,
        }
      : { status: 'absent', position: '', pole: false, fastest_lap: false }
  }
  return rows
}

function ResultForm({ round, onSaved }: { round: RoundDetail; onSaved: () => void }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState(() => initialRows(round))
  const [message, setMessage] = useState<{ kind: 'error' | 'saved'; text: string } | null>(null)
  const [reason, setReason] = useState('')
  const official = round.status === 'official'
  const showPole = round.rules.pole_bonus > 0
  const showFastest = round.rules.fastest_lap_bonus > 0

  function update(entryId: number, change: Partial<Row>) {
    setRows((current) => ({ ...current, [entryId]: { ...current[entryId], ...change } }))
  }

  async function save() {
    setMessage(null)
    const lines = Object.entries(rows)
      .filter(([, row]) => row.status !== 'absent')
      .map(([entryId, row]) => ({
        entry_id: Number(entryId),
        status: row.status as Status,
        position: row.status === 'finished' || row.status === 'dnf' ? Number(row.position) || null : null,
        pole: row.pole,
        fastest_lap: row.fastest_lap,
      }))
    const { error } = await api.PUT('/api/rounds/{round_id}/result', {
      params: { path: { round_id: round.id } },
      body: { lines, reason },
    })
    if (error) setMessage({ kind: 'error', text: errorMessage(t, error) })
    else {
      setReason('')
      setMessage({ kind: 'saved', text: t('round.saved') })
      onSaved()
    }
  }

  return (
    <div className="card result-form">
      <h3>{t('round.enter')}</h3>
      <p className="muted">{t('round.help')}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">{t('season.driver')}</th>
              <th scope="col">{t('round.status')}</th>
              <th scope="col">{t('round.position')}</th>
              {showPole && <th scope="col">{t('round.pole')}</th>}
              {showFastest && <th scope="col">{t('round.fastestLap')}</th>}
            </tr>
          </thead>
          <tbody>
            {round.entries.map((entry) => {
              const row = rows[entry.entry_id]
              const hasPosition = row.status === 'finished' || row.status === 'dnf'
              return (
                <tr key={entry.entry_id}>
                  <td>{entry.number}</td>
                  <td>{entry.driver_name}</td>
                  <td>
                    <select
                      aria-label={`${t('round.status')} ${entry.driver_name}`}
                      value={row.status}
                      onChange={(event) => update(entry.entry_id, { status: event.target.value as Row['status'] })}
                    >
                      {STATUSES.map((status) => (
                        <option key={status} value={status}>
                          {t(`round.statuses.${status}`)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      className="position"
                      aria-label={`${t('round.position')} ${entry.driver_name}`}
                      type="number"
                      min={1}
                      disabled={!hasPosition}
                      value={hasPosition ? row.position : ''}
                      onChange={(event) => update(entry.entry_id, { position: event.target.value })}
                    />
                  </td>
                  {showPole && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`${t('round.pole')} ${entry.driver_name}`}
                        checked={row.pole}
                        onChange={(event) => update(entry.entry_id, { pole: event.target.checked })}
                      />
                    </td>
                  )}
                  {showFastest && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`${t('round.fastestLap')} ${entry.driver_name}`}
                        checked={row.fastest_lap}
                        onChange={(event) => update(entry.entry_id, { fastest_lap: event.target.checked })}
                      />
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {round.status && (
        <label>
          {official ? t('review.reasonRequired') : t('review.reason')}
          <input
            value={reason}
            required={official}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
      )}
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
          {message.text}
        </p>
      )}
      <button type="button" onClick={save}>
        {t('round.save')}
      </button>
    </div>
  )
}
