import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
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
import { AttendanceCard } from './AttendanceCard'
import { Breadcrumbs } from '../components/Breadcrumbs'

type RoundDetail = components['schemas']['RoundDetail']
type Status = components['schemas']['LineIn']['status']
type Row = { status: Status | 'absent'; position: string; pole: boolean; fastest_lap: boolean }

const STATUSES: (Status | 'absent')[] = ['absent', 'finished', 'dnf', 'dns', 'dsq']

const TABS = ['race', 'laps', 'incidents', 'replay', 'restarts', 'telemetry', 'engineer', 'report'] as const
type Tab = (typeof TABS)[number]

export function RoundPage() {
  const { t, i18n } = useTranslation()
  const roundId = Number(useParams().roundId)
  const [search, setSearch] = useSearchParams()
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
  const requested = search.get('tab') as Tab | null
  const tab: Tab = requested && TABS.includes(requested) ? requested : 'race'
  const hasResult = data.result !== null && data.result !== undefined
  const changed = () => {
    round.reload()
    setSaves((n) => n + 1)
  }
  const showTab = (next: Tab) => {
    const params = new URLSearchParams(search)
    if (next === 'race') params.delete('tab')
    else params.set('tab', next)
    setSearch(params, { replace: true })
  }

  const briefing = (
    <>
      <Briefing round={data} />
      <AttendanceCard roundId={data.id} />
      <p>
        <a href={`/api/rounds/${data.id}/calendar.ics`} download>
          {t('calendar.addRound')}
        </a>
      </p>
    </>
  )

  return (
    <section className="round-page">
      <Breadcrumbs
        items={[
          { label: data.championship_name, to: `/championships/${data.championship_id}` },
          { label: data.season_name, to: `/seasons/${data.season_id}` },
          { label: t('round.title', { number: data.number }) },
        ]}
      />
      <header className="round-head">
        <h1 className="round-title">
          <span className="round-number">{t('round.title', { number: data.number })}</span>
          <span>
            {data.track_name} · {data.layout_name}
          </span>
        </h1>
        <p className="muted">{formatDateTime(data.scheduled_at, i18n.language)}</p>
        {data.track_outline_url && (
          <img
            className="round-outline"
            src={data.track_outline_url}
            alt={t('dashboard.outlineAlt', { track: data.track_name, layout: data.layout_name })}
          />
        )}
      </header>

      <nav className="round-tabs" aria-label={t('round.sections')}>
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            aria-current={tab === name ? 'page' : undefined}
            className={tab === name ? 'on' : undefined}
            onClick={() => showTab(name)}
          >
            {t(`round.tabs.${name}`)}
          </button>
        ))}
      </nav>

      {tab === 'race' && (
        <>
          {!hasResult && briefing}

          <h2>{t('round.result')}</h2>
          <StatusBanner round={data} />
          {data.handicap_checks.length > 0 && (
            <div className="data-state" role="status">
              <span className="ds-icon">
                <Icon name="alert" />
              </span>
              <div>
                <p className="ds-title">{t('round.handicapChecks')}</p>
                <ul className="ds-body">
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
            </div>
          )}
          {hasResult ? <ResultTable round={data} /> : <p>{t('round.noResult')}</p>}
          <p className="muted round-rules">
            {t('round.rules', { version: data.rules.version, points: data.rules.points_by_position.join('-') })}{' '}
            {(data.rules.pole_bonus > 0 || data.rules.fastest_lap_bonus > 0) &&
              t('round.bonuses', { pole: data.rules.pole_bonus, fastest: data.rules.fastest_lap_bonus })}
          </p>

          <div className="round-review">
            <div>
              <Penalties round={data} adminView={may('penalties')} onChange={changed} />
            </div>
            <div id="protests">
              <Protests round={data} adminView={may('penalties')} onChange={changed} />
            </div>
          </div>
          <Versions round={data} />

          {hasResult && (
            <details className="round-briefing">
              <summary>{t('round.beforeRace')}</summary>
              {briefing}
            </details>
          )}

          {(may('results') || may('penalties')) && (
            <section className="admin-tools" aria-labelledby="admin-tools">
              <h2 id="admin-tools">
                <Icon name="shield" />
                {t('round.adminTools')}
              </h2>
              {may('results') && <ApproveButton round={data} onChange={changed} />}
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
            </section>
          )}
        </>
      )}

      {tab === 'laps' && <LapsSection key={`${imports}-${saves}`} roundId={data.id} />}
      {tab === 'incidents' && <IncidentsSection roundId={data.id} />}
      {tab === 'replay' && <ReplaySection roundId={data.id} />}
      {tab === 'restarts' && (
        <RestartsSection roundId={data.id} entries={data.entries} adminView={may('restarts')} refresh={saves} />
      )}
      {tab === 'telemetry' && <TelemetrySection roundId={data.id} />}
      {tab === 'engineer' && <EngineerSection roundId={data.id} />}
      {tab === 'report' && <ReportSection target={{ kind: 'round', id: data.id }} adminView={may('reports')} />}
    </section>
  )
}

/** The state of the result: provisional with the protest deadline, or official. */
function StatusBanner({ round }: { round: RoundDetail }) {
  const { t, i18n } = useTranslation()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  if (!round.status) return null
  const official = round.status === 'official'
  const deadline = round.protest_deadline
  const minutesLeft = deadline ? Math.ceil((new Date(deadline).getTime() - now) / 60_000) : null
  return (
    <div className={`status-banner ${official ? 'official' : 'provisional'}`} role="status">
      <span className="status-icon">
        <Icon name={official ? 'check' : 'clock'} />
      </span>
      <div>
        <div className="status-title">
          <ResultStatus round={round} />
        </div>
        <p className="muted">{official ? t('round.officialHelp') : t('round.provisionalHelp')}</p>
      </div>
      {!official && deadline && (
        <div className="status-clock">
          <b>{formatTime(deadline, i18n.language)}</b>
          <span>
            {round.protest_window_open && minutesLeft !== null && minutesLeft > 0
              ? t('round.minutesLeft', { count: minutesLeft })
              : t('round.windowClosed')}
          </span>
          {round.can_protest && (
            <a className="small-link" href="#protests">
              {t('round.protestLink')}
            </a>
          )}
        </div>
      )}
    </div>
  )
}

function formatTime(iso: string, language: string): string {
  return new Intl.DateTimeFormat(language, { hour: '2-digit', minute: '2-digit' }).format(new Date(iso))
}

function ResultTable({ round }: { round: RoundDetail }) {
  const { t } = useTranslation()
  const lines = round.result ?? []
  const rules = round.rules
  const hasIncidents = lines.some((line) => line.incidents !== null && line.incidents !== undefined)
  const timeOrGap = (line: (typeof lines)[number]) => {
    if (line.laps_down) return t('round.lapsDown', { count: line.laps_down })
    if (line.gap_ms !== null && line.gap_ms !== undefined) return `+${(line.gap_ms / 1000).toFixed(3)}`
    return formatLapTime(line.total_ms)
  }
  return (
    <div className="table-wrap results-table">
      <table>
        <thead>
          <tr>
            <th scope="col">{t('round.position')}</th>
            <th scope="col">{t('season.driver')}</th>
            <th scope="col" className="r hide-sm">
              {t('round.laps')}
            </th>
            <th scope="col" className="r">
              {t('round.timeGap')}
            </th>
            {hasIncidents && (
              <th scope="col" className="r hide-sm">
                {t('round.incidents')}
              </th>
            )}
            <th scope="col" className="r">
              {t('round.points')}
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.entry_id} className={line.status === 'dns' || line.status === 'dsq' ? 'dim' : undefined}>
              <td className="pos">{line.position ?? t(`round.short.${line.status}`)}</td>
              <td>
                <span className="car-number">#{line.number}</span>
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
              <td className="r hide-sm">{line.laps ?? '—'}</td>
              <td className="r">{timeOrGap(line)}</td>
              {hasIncidents && <td className="r hide-sm">{line.incidents ?? '—'}</td>}
              <td className="r points">{line.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
