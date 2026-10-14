import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, readCookie } from '../api/client'
import { FileDrop } from '../components/FileDrop'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime, formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Entry = components['schemas']['EntryOption']
type ImportOut = components['schemas']['ImportOut']
type Matched = components['schemas']['MatchedOut']

/** Upload an AC result file, check the preview, and apply it. Admin mode only. */
export function ImportSection({
  roundId,
  entries,
  onApplied,
}: {
  roundId: number
  entries: Entry[]
  onApplied: () => void
}) {
  const { t, i18n } = useTranslation()
  const path = { round_id: roundId }
  const imports = useLoad(() => api.GET('/api/rounds/{round_id}/imports', { params: { path } }), [roundId])
  const [current, setCurrent] = useState<ImportOut | null>(null)
  const [message, setMessage] = useState<{ kind: 'error' | 'status'; text: string } | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage(null)
    const form = new FormData(event.currentTarget)
    // A file upload goes with a plain fetch. The typed client sends JSON.
    let response: Response
    try {
      response = await fetch(`/api/rounds/${roundId}/imports`, {
        method: 'POST',
        body: form,
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
      })
    } catch {
      setMessage({ kind: 'error', text: t('errors.generic') })
      return
    }
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      setMessage({ kind: 'error', text: errorMessage(t, body) })
      return
    }
    const data = body as ImportOut
    setCurrent(data)
    if (!data.is_new) setMessage({ kind: 'status', text: t('imports.sameFile') })
    imports.reload()
  }

  async function open(importId: number) {
    setMessage(null)
    const { data } = await api.GET('/api/imports/{import_id}', {
      params: { path: { import_id: importId } },
    })
    if (data) setCurrent(data)
  }

  return (
    <div className="card import">
      <h3>{t('imports.title')}</h3>
      <p className="muted">{t('imports.help')}</p>
      <form className="upload" onSubmit={submit} aria-label={t('imports.title')}>
        <FileDrop label={t('imports.file')} name="file" accept=".json,application/json" required />
        <button type="submit">{t('imports.upload')}</button>
      </form>
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'muted'}>
          {message.text}
        </p>
      )}

      {current?.preview && (
        <Preview
          key={`${current.id}-${current.status}`}
          item={current}
          entries={entries}
          onChange={(next) => {
            setCurrent(next)
            imports.reload()
            if (next.status === 'applied') onApplied()
          }}
        />
      )}

      {imports.data && imports.data.length > 0 && (
        <>
          <h4>{t('imports.previous')}</h4>
          <ul className="list">
            {imports.data.map((item) => (
              <li key={item.id}>
                <button type="button" className="link" onClick={() => open(item.id)}>
                  {item.filename}
                </button>{' '}
                <span className="badge">{t(`imports.session.${item.session_type}`)}</span>
                <span className="badge">{t(`imports.status.${item.status}`)}</span>
                {item.auto_status && (
                  <span className={`badge auto-${item.auto_status}`}>{t(`imports.auto.${item.auto_status}`)}</span>
                )}
                <span className="muted">
                  {' '}
                  {item.uploaded_by ?? t('imports.byCollector')} · {formatDateTime(item.uploaded_at, i18n.language)}
                </span>
                {item.status === 'preview' && (item.auto_reasons ?? []).length > 0 && (
                  <ul className="auto-notes">
                    {(item.auto_reasons ?? []).map((reason) => (
                      <li key={reason}>
                        {t(`imports.autoReasons.${reason}`, {
                          defaultValue: t(`imports.warnings.${reason}`, { defaultValue: reason }),
                        })}
                      </li>
                    ))}
                  </ul>
                )}
                {(item.review_flags ?? []).length > 0 && (
                  <p className="auto-notes">
                    {t('imports.checkDnf', {
                      names: (item.review_flags ?? [])
                        .map((flag) => entries.find((e) => e.entry_id === flag.entry_id)?.driver_name ?? `#${flag.entry_id}`)
                        .join(', '),
                    })}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function Preview({
  item,
  entries,
  onChange,
}: {
  item: ImportOut
  entries: Entry[]
  onChange: (next: ImportOut) => void
}) {
  const { t } = useTranslation()
  const preview = item.preview!
  const [statuses, setStatuses] = useState<Record<number, string>>({})
  const [ignored, setIgnored] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const applied = item.status === 'applied'
  const isRace = preview.session_type === 'race'

  async function link(guid: string, entryId: string) {
    setError(null)
    const { data, error } = await api.POST('/api/imports/{import_id}/link', {
      params: { path: { import_id: item.id } },
      body: { guid, entry_id: Number(entryId) },
    })
    if (error || !data) setError(errorMessage(t, error))
    else onChange(data)
  }

  async function applyFile() {
    setError(null)
    const { data, error } = await api.POST('/api/imports/{import_id}/apply', {
      params: { path: { import_id: item.id } },
      body: { statuses, ignored_guids: ignored },
    })
    if (error || !data) setError(errorMessage(t, error))
    else onChange(data)
  }

  return (
    <section className="preview" aria-label={t('imports.preview')}>
      <h4>
        {t('imports.preview')}: {item.filename}{' '}
        <span className="badge">{t(`imports.session.${preview.session_type}`)}</span>
        <span className="badge">{t(`imports.status.${item.status}`)}</span>
      </h4>
      <p className="muted">
        {preview.track} · {preview.layout || '—'}
        {preview.attempt && ` · ${t('imports.attempt', { number: preview.attempt })}`}
      </p>
      {!isRace && <p className="muted">{t('imports.qualifyingNote')}</p>}
      {preview.warnings.map((warning) => (
        <p key={warning} className="warning">
          {t(`imports.warnings.${warning}`)}
        </p>
      ))}

      <h5>{t('imports.matched')}</h5>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('round.position')}</th>
              <th scope="col">{t('season.driver')}</th>
              <th scope="col">GUID</th>
              <th scope="col">{t('imports.laps')}</th>
              <th scope="col">{t('imports.totalTime')}</th>
              <th scope="col">{t('imports.bestLap')}</th>
              <th scope="col">{t('imports.handicap')}</th>
              {isRace && !applied && <th scope="col">{t('imports.finalStatus')}</th>}
            </tr>
          </thead>
          <tbody>
            {preview.drivers.map((driver) => (
              <DriverRow
                key={driver.guid}
                driver={driver}
                showStatus={isRace && !applied}
                status={statuses[driver.entry_id!] ?? 'finished'}
                onStatus={(value) => setStatuses((s) => ({ ...s, [driver.entry_id!]: value }))}
              />
            ))}
          </tbody>
        </table>
      </div>

      {preview.unmatched.length > 0 && (
        <>
          <h5>{t('imports.unmatched')}</h5>
          <p className="muted">{t('imports.unmatchedHelp')}</p>
          <ul className="list">
            {preview.unmatched.map((driver) => (
              <li key={driver.guid} className="unmatched">
                <strong>{driver.name}</strong> <span className="mono muted">{driver.guid}</span> ·{' '}
                {driver.laps} {t('imports.laps').toLowerCase()}
                {!applied && (
                  <>
                    <label className="inline">
                      {t('imports.linkTo')}
                      <select
                        aria-label={`${t('imports.linkTo')} ${driver.name}`}
                        defaultValue=""
                        onChange={(event) => event.target.value && link(driver.guid, event.target.value)}
                      >
                        <option value="">{t('common.select')}</option>
                        {entries.map((entry) => (
                          <option key={entry.entry_id} value={entry.entry_id}>
                            #{entry.number} {entry.driver_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="check inline">
                      <input
                        type="checkbox"
                        checked={ignored.includes(driver.guid)}
                        onChange={(event) =>
                          setIgnored((list) =>
                            event.target.checked ? [...list, driver.guid] : list.filter((g) => g !== driver.guid),
                          )
                        }
                      />
                      {t('imports.ignore')}
                    </label>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <h5>{t('imports.missing')}</h5>
      <p className="muted">{preview.missing.map((code) => t(`imports.missingFields.${code}`)).join(' · ')}</p>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {applied ? (
        <p role="status" className="success">
          {t('imports.applied')}
        </p>
      ) : (
        <button type="button" onClick={applyFile}>
          {t('imports.apply')}
        </button>
      )}
    </section>
  )
}

function DriverRow({
  driver,
  showStatus,
  status,
  onStatus,
}: {
  driver: Matched
  showStatus: boolean
  status: string
  onStatus: (value: string) => void
}) {
  const { t } = useTranslation()
  return (
    <tr>
      <td>{driver.position}</td>
      <td>
        {driver.driver_name}
        {driver.name !== driver.driver_name && <span className="muted"> ({driver.name})</span>}
        {driver.warnings.map((warning) => (
          <span key={warning} className="badge warn" title={t(`imports.warnings.${warning}`)}>
            !
          </span>
        ))}
        {driver.warnings.includes('handicap_differs') && (
          <div className="warning">
            {t('imports.handicapDiffers', {
              assignedKg: driver.assigned_ballast_kg,
              assignedPct: driver.assigned_restrictor,
              fileKg: driver.ballast_kg,
              filePct: driver.restrictor,
            })}
          </div>
        )}
      </td>
      <td className="mono muted">{driver.guid}</td>
      <td>{driver.laps}</td>
      <td>{formatLapTime(driver.total_time_ms)}</td>
      <td>{formatLapTime(driver.best_lap_ms)}</td>
      <td>
        {driver.ballast_kg} kg / {driver.restrictor} %
      </td>
      {showStatus && (
        <td>
          <select
            aria-label={`${t('imports.finalStatus')} ${driver.driver_name}`}
            value={status}
            onChange={(event) => onStatus(event.target.value)}
          >
            <option value="finished">{t('round.statuses.finished')}</option>
            <option value="dnf">{t('round.statuses.dnf')}</option>
          </select>
        </td>
      )}
    </tr>
  )
}
