import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
import { errorMessage } from '../lib/errors'
import { formatLapTime } from '../lib/format'
import { pointAt } from '../lib/telemetryMath'
import { fit, polyline, trackOutline } from '../lib/trackMap'
import { useLoad } from '../lib/useLoad'
import { TabEmpty } from './TabEmpty'

type Engineer = components['schemas']['EngineerOut']
type Corner = components['schemas']['CornerOut']
type Cause = components['schemas']['CauseOut']
type Session = 'race' | 'qualifying' | 'practice'

const TOP = 3

/** The race engineer: where the driver loses time in each corner, and why, from the pedals and
 * the speed, against a reference lap. An AI note can sum it up. */
export function EngineerSection({ roundId }: { roundId: number }) {
  const { t, i18n } = useTranslation()
  const [session, setSession] = useState<Session>('race')
  const [driver, setDriver] = useState<number | null>(null)
  const [lap, setLap] = useState<number | null>(null)
  const [reference, setReference] = useState<string | null>(null)
  const query = {
    session,
    ...(driver ? { driver } : {}),
    ...(lap ? { lap } : {}),
    ...(reference ? { reference } : {}),
  }
  const load = useLoad(
    () => api.GET('/api/rounds/{round_id}/engineer', { params: { path: { round_id: roundId }, query } }),
    [roundId, session, driver, lap, reference],
  )
  const map = useLoad(
    () => api.GET('/api/rounds/{round_id}/track-map', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const [selected, setSelected] = useState<number | null>(null)
  const data = load.data

  // A note that the worker still writes: ask again every 3 seconds.
  const pending = data?.note?.status === 'pending'
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => load.reload(), 3000)
    return () => window.clearInterval(timer)
  }, [pending, load])

  if (!data) return null
  const head = (
    <div className="section-head">
      <h2>{t('engineer.title')}</h2>
      <div className="tabs" role="tablist">
        {(['race', 'qualifying', 'practice'] as const).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={name === session}
            className={name === session ? 'active' : undefined}
            onClick={() => {
              setSession(name)
              setLap(null)
              setReference(null)
            }}
          >
            {t(`telemetryTool.sessions.${name}`)}
          </button>
        ))}
      </div>
    </div>
  )
  if (data.gaps.includes('no_driver')) {
    return (
      <TabEmpty heading={t('engineer.title')} icon="user" title={t('tabEmpty.noProfile')} text={t('tabEmpty.engineerProfile')}>
        <Link className="small-link" to="/">
          {t('tabEmpty.goHome')}
        </Link>
      </TabEmpty>
    )
  }

  const picker = (
    <div className="eng-controls">
      {data.drivers.length > 0 && (
        <label>
          {t('engineer.driver')}
          <select
            value={data.driver?.id ?? ''}
            onChange={(event) => {
              setDriver(Number(event.target.value))
              setLap(null)
              setReference(null)
            }}
          >
            {data.drivers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {data.laps.length > 0 && (
        <label>
          {t('engineer.yourLap')}
          <select value={data.lap?.id ?? ''} onChange={(event) => setLap(Number(event.target.value))}>
            {data.laps.map((item) => (
              <option key={item.id} value={item.id}>
                {t('telemetryTool.lapShort', { number: item.lap_number })} · {formatLapTime(item.lap_time_ms)}
              </option>
            ))}
          </select>
        </label>
      )}
      {data.laps.length > 0 && (
        <label>
          {t('engineer.compareWith')}
          <select
            value={data.reference ? String(data.reference.id) : 'own'}
            onChange={(event) => setReference(event.target.value)}
          >
            {data.reference_options.map((item) => (
              <option key={item.id} value={item.id}>
                {item.driver_name} · {t('telemetryTool.lapShort', { number: item.lap_number })} · {formatLapTime(item.lap_time_ms)}
              </option>
            ))}
            {data.laps
              .filter((item) => item.id !== data.lap?.id)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {t('engineer.ownLap', { number: item.lap_number, time: formatLapTime(item.lap_time_ms) })}
                </option>
              ))}
            <option value="own">{t('engineer.ownBest')}</option>
          </select>
        </label>
      )}
    </div>
  )

  if (data.gaps.includes('no_laps') || !data.lap) {
    return (
      <section aria-label={t('engineer.title')}>
        {head}
        {picker}
        <TabEmpty heading="" icon="timer" title={t('tabEmpty.noOwnLaps')} text={t('engineer.noLaps')} />
      </section>
    )
  }

  const lapTime = data.lap.lap_time_ms / 1000
  const refTime = data.reference ? data.reference.lap_time_ms / 1000 : data.ideal_s
  const gap = refTime !== null && refTime !== undefined ? lapTime - refTime : null
  const losing = [...data.corners]
    .filter((corner) => (corner.loss_s ?? 0) >= 0.04)
    .sort((a, b) => (b.loss_s ?? 0) - (a.loss_s ?? 0))
  const top = losing.slice(0, TOP)
  const telemetryLink = (corner: Corner) => {
    const pad = 0.01
    const ids = [data.lap!.id, corner.reference_lap_id].filter((id, i, all) => all.indexOf(id) === i)
    return `?tab=telemetry&laps=${ids.join(',')}&ref=${corner.reference_lap_id}&from=${Math.max(0, corner.start - pad).toFixed(4)}&to=${Math.min(1, corner.end + pad).toFixed(4)}`
  }

  return (
    <section className="eng" aria-label={t('engineer.title')}>
      {head}
      {picker}

      <div className="eng-summary">
        <div>
          <span className="muted">{t('engineer.yourLap')}</span>
          <b>{formatLapTime(data.lap.lap_time_ms)}</b>
        </div>
        <div>
          <span className="muted">{data.reference ? t('engineer.reference', { name: data.reference.driver_name }) : t('engineer.ownBest')}</span>
          <b>{refTime !== null && refTime !== undefined ? formatLapTime(Math.round(refTime * 1000)) : '—'}</b>
        </div>
        <div>
          <span className="muted">{t('engineer.gap')}</span>
          <b className={gap !== null && gap > 0 ? 'slower' : 'faster'}>{gap === null ? '—' : `${gap > 0 ? '+' : ''}${gap.toFixed(3)} s`}</b>
        </div>
        {data.ideal_s !== null && data.ideal_s !== undefined && (
          <div>
            <span className="muted">{t('engineer.ideal')}</span>
            <b>{formatLapTime(Math.round(data.ideal_s * 1000))}</b>
            <small className="muted">{t('engineer.idealGain', { seconds: (lapTime - data.ideal_s).toFixed(2) })}</small>
          </div>
        )}
      </div>
      {!data.has_pedals && <p className="muted">{t('engineer.noPedals')}</p>}

      <div className="eng-body">
        <CornerMap
          map={map.data ?? null}
          corners={data.corners}
          selected={selected}
          onSelect={(number) => {
            setSelected(number)
            document.getElementById(`eng-corner-${number}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
          }}
        />
        <div className="eng-top">
          <h3>{t('engineer.whereToGain')}</h3>
          {top.length === 0 ? (
            <p className="muted">{t('engineer.nothingToGain')}</p>
          ) : (
            top.map((corner) => (
              <article key={corner.number} className={selected === corner.number ? 'eng-card on' : 'eng-card'}>
                <header>
                  <b>{t('engineer.corner', { number: corner.number })}</b>
                  <span className="eng-loss">+{(corner.loss_s ?? 0).toFixed(2)} s</span>
                </header>
                {corner.causes.length === 0 ? (
                  <p className="muted">{t('engineer.noCause')}</p>
                ) : (
                  <ul className="eng-causes">
                    {corner.causes.map((cause) => (
                      <li key={cause.kind}>
                        <span>{causeText(t, cause)}</span>
                        <small className="muted">{t(`engineer.try.${cause.kind}`)}</small>
                      </li>
                    ))}
                  </ul>
                )}
                <Link className="small-link" to={telemetryLink(corner)}>
                  {t('engineer.openTelemetry')}
                  <Icon name="arrow" small />
                </Link>
              </article>
            ))
          )}
        </div>
      </div>

      <Note
        roundId={roundId}
        data={data}
        query={{ session, driver: driver ?? undefined, lap: lap ?? undefined, reference: reference ?? undefined }}
        language={i18n.language.startsWith('en') ? 'en' : 'es'}
        onChange={load.reload}
      />

      <h3>{t('engineer.allCorners')}</h3>
      <div className="table-wrap">
        <table className="eng-table">
          <thead>
            <tr>
              <th scope="col">{t('engineer.cornerShort')}</th>
              <th scope="col" className="r">{t('engineer.time')}</th>
              <th scope="col" className="r">{t('engineer.brake')}</th>
              <th scope="col" className="r">{t('engineer.minSpeed')}</th>
              <th scope="col" className="r">{t('engineer.throttle')}</th>
              <th scope="col" className="r">{t('engineer.exit')}</th>
              <th scope="col" className="r">{t('engineer.gear')}</th>
              <th scope="col">
                <span className="sr-only">{t('engineer.openTelemetry')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.corners.map((corner) => (
              <tr key={corner.number} id={`eng-corner-${corner.number}`} className={selected === corner.number ? 'on' : undefined}>
                <th scope="row">{corner.number}</th>
                <td className={`r ${tone(corner.loss_s, 0.04)}`}>{signed(corner.loss_s, 2, ' s')}</td>
                <td className="r">{pair(corner.yours.brake_m, corner.reference.brake_m, 'm', true)}</td>
                <td className="r">{pair(corner.yours.min_kmh, corner.reference.min_kmh, 'km/h')}</td>
                <td className="r">{pair(corner.yours.throttle_m, corner.reference.throttle_m, 'm', true)}</td>
                <td className="r">{pair(corner.yours.exit_kmh, corner.reference.exit_kmh, 'km/h')}</td>
                <td className="r">
                  {corner.yours.gear ?? '—'}
                  {corner.reference.gear !== null && corner.reference.gear !== corner.yours.gear && <small className="muted"> / {corner.reference.gear}</small>}
                </td>
                <td>
                  <Link className="icon-button" to={telemetryLink(corner)} aria-label={t('engineer.openTelemetryFor', { number: corner.number })}>
                    <Icon name="arrow" small />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted note">{t('engineer.tableHelp')}</p>

      {data.spread.length > 0 && (
        <>
          <h3>{t('engineer.consistency')}</h3>
          <ul className="eng-spread">
            {data.spread.slice(0, TOP).map((item) => (
              <li key={item.number}>
                <b>{t('engineer.corner', { number: item.number })}</b>
                <span>{t('engineer.spreadText', { best: item.best_s.toFixed(2), worst: item.worst_s.toFixed(2), spread: item.time_s.toFixed(2) })}</span>
                {item.brake_m !== null && item.brake_m !== undefined && item.brake_m >= 5 && (
                  <small className="muted">{t('engineer.spreadBrake', { meters: Math.round(item.brake_m) })}</small>
                )}
                {item.min_kmh !== null && item.min_kmh !== undefined && item.min_kmh >= 3 && (
                  <small className="muted">{t('engineer.spreadMin', { kmh: Math.round(item.min_kmh) })}</small>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted note">{t('engineer.caution')}</p>
    </section>
  )
}

function tone(value: number | null | undefined, limit: number) {
  if (value === null || value === undefined) return ''
  return value >= limit ? 'slower' : value <= -limit ? 'faster' : ''
}

function signed(value: number | null | undefined, digits: number, unit: string) {
  if (value === null || value === undefined) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}${unit}`
}

/** Your value and the difference with the reference. Distances: smaller is earlier. */
function pair(mine: number | null | undefined, ref: number | null | undefined, unit: string, distance = false) {
  if (mine === null || mine === undefined) return '—'
  if (ref === null || ref === undefined) return `${Math.round(mine)} ${unit}`
  const difference = Math.round(mine - ref)
  return (
    <>
      {Math.round(mine)} {unit}
      {difference !== 0 && (
        <small className={distance ? 'muted' : difference < 0 ? 'slower' : 'faster'}> ({difference > 0 ? '+' : ''}{difference})</small>
      )}
    </>
  )
}

function causeText(t: (key: string, values?: Record<string, unknown>) => string, cause: Cause) {
  return t(`engineer.cause.${cause.kind}`, {
    yours: Math.round(cause.yours),
    reference: Math.round(cause.reference),
    difference: Math.abs(Math.round(cause.difference)),
  })
}

/** The track with a numbered dot at each corner: red where the driver loses time, green where
 * the driver gains time. */
function CornerMap({
  map,
  corners,
  selected,
  onSelect,
}: {
  map: components['schemas']['TrackMapOut'] | null
  corners: Corner[]
  selected: number | null
  onSelect: (number: number) => void
}) {
  const { t } = useTranslation()
  const outline = trackOutline(map, [])
  if (!map || outline.length < 10) return <div className="eng-map empty muted">{t('telemetryTool.noMap')}</div>
  const size = 400
  const place = fit(outline, size, 26)
  return (
    <figure className="eng-map">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={t('engineer.map')}>
        <polyline className="tm-track" points={polyline(outline, place)} />
        {corners.map((corner) => {
          const at = pointAt(map, corner.apex)
          if (!at) return null
          const [cx, cy] = place(at)
          const loss = corner.loss_s ?? 0
          const kind = loss >= 0.04 ? 'lose' : loss <= -0.04 ? 'gain' : 'even'
          return (
            <g
              key={corner.number}
              className={`eng-pin ${kind} ${selected === corner.number ? 'on' : ''}`}
              role="button"
              tabIndex={0}
              aria-label={t('engineer.pin', { number: corner.number, loss: signed(corner.loss_s, 2, ' s') })}
              onClick={() => onSelect(corner.number)}
              onKeyDown={(event) => event.key === 'Enter' && onSelect(corner.number)}
            >
              <circle cx={cx} cy={cy} r={13} />
              <text x={cx} y={cy + 4} textAnchor="middle">
                {corner.number}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="muted">{t('engineer.mapHelp')}</figcaption>
    </figure>
  )
}

/** The AI note: a short summary of the numbers, like a race engineer on the radio. */
function Note({
  roundId,
  data,
  query,
  language,
  onChange,
}: {
  roundId: number
  data: Engineer
  query: { session: Session; driver?: number; lap?: number; reference?: string }
  language: 'es' | 'en'
  onChange: () => void
}) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const note = data.note

  async function ask() {
    setError(null)
    setBusy(true)
    const { error } = await api.POST('/api/rounds/{round_id}/engineer/note', {
      params: { path: { round_id: roundId } },
      body: { ...query, language },
    })
    setBusy(false)
    if (error) setError(errorMessage(t, error))
    else onChange()
  }

  return (
    <div className="eng-note">
      <div className="eng-note-head">
        <span className="eng-note-icon" aria-hidden="true">
          <Icon name="info" small />
        </span>
        <b>{t('engineer.noteTitle')}</b>
      </div>
      {note?.status === 'ready' && <p className="eng-note-text">{note.text}</p>}
      {note?.status === 'pending' && (
        <p className="muted" role="status">
          <span className="spinner" aria-hidden="true" /> {t('engineer.noteWriting')}
        </p>
      )}
      {note?.status === 'failed' && <p className="error">{t('engineer.noteFailed')}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!data.ai_available ? (
        <p className="muted">{t('engineer.noAi')}</p>
      ) : (
        note?.status !== 'pending' &&
        note?.status !== 'ready' && (
          <button type="button" onClick={ask} disabled={busy}>
            {t('engineer.askNote')}
          </button>
        )
      )}
      {data.ai_available && <small className="muted">{t('engineer.noteHelp')}</small>}
    </div>
  )
}
