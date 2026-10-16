import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
import { formatLapTime } from '../lib/format'
import { CHANNELS, delta, fastestByPart, grid, toGrid, type Channel, type GridLap } from '../lib/telemetryMath'
import { useLoad } from '../lib/useLoad'
import { TabEmpty } from './TabEmpty'
import { TelemetryChart, type Lane, type LaneDef, type SeriesDef, type View } from './telemetry/TelemetryChart'
import { TelemetryMap } from './telemetry/TelemetryMap'

type LapRow = components['schemas']['LapOut']
type LapDetail = components['schemas']['LapDetailOut']
type Lane2 = 'delta' | Channel

const LAP_COLORS = ['#e10600', '#38bdf8', '#facc15', '#4ade80', '#c084fc', '#fb923c']
const MAX_LAPS = LAP_COLORS.length
const SESSIONS = ['race', 'qualifying', 'practice'] as const
const DEFAULT_LANES: Lane2[] = ['delta', 'speed_kmh', 'gas', 'brake', 'steer', 'gear']
const MAP_PARTS = 60

/** The telemetry tool of a round: pick laps of any driver, see them on one lap distance, zoom,
 * and compare them with a time delta and the track map. */
export function TelemetrySection({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const laps = useLoad(
    () => api.GET('/api/rounds/{round_id}/telemetry', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const map = useLoad(
    () => api.GET('/api/rounds/{round_id}/track-map', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  if (!laps.data) return null
  if (laps.data.length === 0) {
    return (
      <TabEmpty
        heading={t('telemetry.roundTitle')}
        icon="timer"
        title={t('tabEmpty.noTelemetry')}
        text={t('tabEmpty.telemetry')}
      />
    )
  }
  return <Workbench laps={laps.data} map={map.data ?? null} />
}

function bestOf(laps: LapRow[]): LapRow | undefined {
  return [...laps].sort((a, b) => Number(b.valid) - Number(a.valid) || a.lap_time_ms - b.lap_time_ms)[0]
}

/** The laps that the tool shows first: the best lap of each driver, or the 2 best laps of a
 * single driver. */
function firstPick(laps: LapRow[]): number[] {
  const drivers = [...new Set(laps.map((lap) => lap.driver_name))]
  if (drivers.length === 1) {
    return [...laps]
      .filter((lap) => lap.valid)
      .sort((a, b) => a.lap_time_ms - b.lap_time_ms)
      .slice(0, 2)
      .map((lap) => lap.id)
  }
  return drivers
    .map((name) => bestOf(laps.filter((lap) => lap.driver_name === name)))
    .filter((lap): lap is LapRow => lap !== undefined)
    .sort((a, b) => a.lap_time_ms - b.lap_time_ms)
    .slice(0, 3)
    .map((lap) => lap.id)
}

function Workbench({
  laps,
  map,
}: {
  laps: LapRow[]
  map: components['schemas']['TrackMapOut'] | null
}) {
  const { t } = useTranslation()
  // A link (from the race engineer) can choose the laps, the reference, and the part of the lap.
  const [search] = useSearchParams()
  const linked = (search.get('laps') ?? '')
    .split(',')
    .map(Number)
    .filter((id) => laps.some((lap) => lap.id === id))
  const sessions = SESSIONS.filter((s) => laps.some((lap) => lap.session_type === s))
  const [session, setSession] = useState<string>(
    () => laps.find((lap) => lap.id === linked[0])?.session_type ?? sessions[0] ?? laps[0].session_type,
  )
  const inSession = useMemo(() => laps.filter((lap) => lap.session_type === session), [laps, session])
  const [picked, setPicked] = useState<number[]>(() => (linked.length > 0 ? linked : firstPick(inSession)))
  const [reference, setReference] = useState<number | null>(() => {
    const id = Number(search.get('ref'))
    return linked.includes(id) ? id : null
  })
  const [lanes, setLanes] = useState<Lane2[]>(DEFAULT_LANES)
  const [details, setDetails] = useState<Record<number, LapDetail>>({})
  // The part of the lap on the chart, from 0 to 1. Null: the whole lap.
  const [part, setPart] = useState<View | null>(() => {
    const from = Number(search.get('from'))
    const to = Number(search.get('to'))
    return search.get('from') && to > from ? [Math.max(0, from), Math.min(1, to)] : null
  })
  const [cursor, setCursor] = useState<number | null>(null)

  // Fetch the samples of each picked lap one time.
  useEffect(() => {
    const missing = picked.filter((id) => !details[id])
    if (missing.length === 0) return
    let stop = false
    Promise.all(
      missing.map((id) => api.GET('/api/telemetry-laps/{lap_id}', { params: { path: { lap_id: id } } })),
    ).then((answers) => {
      if (stop) return
      setDetails((old) => {
        const next = { ...old }
        answers.forEach(({ data }) => {
          if (data) next[data.id] = data
        })
        return next
      })
    })
    return () => {
      stop = true
    }
  }, [picked, details])

  const rows = picked.map((id) => laps.find((lap) => lap.id === id)).filter((lap): lap is LapRow => !!lap)
  const ready = rows.filter((lap) => details[lap.id])
  const gridLaps = useMemo(
    () => ready.map((lap) => toGrid({ id: lap.id, channels: details[lap.id].channels })),
    // The grid changes only when the set of loaded laps changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready.map((lap) => lap.id).join(','), Object.keys(details).length],
  )
  const fastestPicked = bestOf(ready)
  const referenceId = reference !== null && picked.includes(reference) ? reference : (fastestPicked?.id ?? null)
  const refGrid = gridLaps.find((lap) => lap.id === referenceId) ?? null
  const length = map?.length_m ?? null
  const x = useMemo(() => grid.map((s) => (length ? s * length : s * 100)), [length])
  const xLabel = (value: number) => (length ? `${Math.round(value)} m` : `${value.toFixed(1)} %`)
  const toS = (value: number) => (length ? value / length : value / 100)
  const colorOf = (id: number) => LAP_COLORS[picked.indexOf(id) % LAP_COLORS.length]

  const series: SeriesDef[] = useMemo(
    () => ready.map((lap) => ({ label: lapName(lap, t), color: colorOf(lap.id) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gridLaps, picked],
  )

  const laneDefs: Record<Lane2, LaneDef> = {
    delta: { key: 'delta', label: t('telemetryTool.lanes.delta'), unit: 's', height: 110, digits: 2, zero: true },
    speed_kmh: { key: 'speed_kmh', label: t('telemetryTool.lanes.speed_kmh'), unit: 'km/h', height: 190, digits: 0 },
    gas: { key: 'gas', label: t('telemetryTool.lanes.gas'), unit: '%', height: 90, digits: 0, range: [-4, 104] },
    brake: { key: 'brake', label: t('telemetryTool.lanes.brake'), unit: '%', height: 90, digits: 0, range: [-4, 104] },
    steer: { key: 'steer', label: t('telemetryTool.lanes.steer'), unit: '°', height: 110, digits: 0, zero: true },
    gear: { key: 'gear', label: t('telemetryTool.lanes.gear'), unit: '', height: 80, digits: 0, step: true },
    rpm: { key: 'rpm', label: t('telemetryTool.lanes.rpm'), unit: 'rpm', height: 110, digits: 0 },
  }
  const shownLanes = lanes.filter((lane) => lane !== 'delta' || (gridLaps.length > 1 && refGrid))
  const chartLanes: Lane[] = useMemo(
    () =>
      shownLanes.map((lane) => ({
        def: laneDefs[lane],
        values: gridLaps.map((lap) =>
          lane === 'delta' ? (refGrid ? delta(lap, refGrid) : grid.map(() => null)) : lap.values[lane],
        ),
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gridLaps, shownLanes.join(','), refGrid, t],
  )
  const fastest = useMemo(
    () => (gridLaps.length > 1 ? fastestByPart(gridLaps, MAP_PARTS) : []),
    [gridLaps],
  )

  function toggle(id: number) {
    setPicked((old) => {
      if (old.includes(id)) return old.filter((other) => other !== id)
      if (old.length >= MAX_LAPS) return old
      return [...old, id]
    })
  }

  function chooseSession(next: string) {
    setSession(next)
    setPicked(firstPick(laps.filter((lap) => lap.session_type === next)))
    setReference(null)
    setView(null)
  }

  const fullView: View = [x[0], x[x.length - 1]]
  const end = x[x.length - 1] || 1
  const currentView: View = part ? [part[0] * end, part[1] * end] : fullView
  const setView = (next: View | null) => setPart(next ? [next[0] / end, next[1] / end] : null)
  const zoom = (factor: number) => {
    const middle = (currentView[0] + currentView[1]) / 2
    const half = ((currentView[1] - currentView[0]) * factor) / 2
    const span = fullView[1] - fullView[0]
    const size = Math.min(span, Math.max(half * 2, span * 0.004))
    const min = Math.min(Math.max(fullView[0], middle - size / 2), fullView[1] - size)
    setView([min, min + size])
  }
  const byDriver = [...new Set(inSession.map((lap) => lap.driver_name))].map((name) => ({
    name,
    laps: inSession.filter((lap) => lap.driver_name === name).sort((a, b) => a.lap_number - b.lap_number),
  }))
  const sessionBest = bestOf(inSession)

  return (
    <section className="tm" aria-label={t('telemetry.roundTitle')}>
      <div className="section-head">
        <h2>{t('telemetry.roundTitle')}</h2>
        {sessions.length > 1 && (
          <div className="tabs" role="tablist">
            {sessions.map((s) => (
              <button key={s} type="button" role="tab" aria-selected={s === session} className={s === session ? 'active' : undefined} onClick={() => chooseSession(s)}>
                {t(`telemetryTool.sessions.${s}`)}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="tm-picker">
        {byDriver.map((driver) => (
          <div key={driver.name} className="tm-driver">
            <b>{driver.name}</b>
            <div className="tm-laps">
              {driver.laps.map((lap) => {
                const on = picked.includes(lap.id)
                return (
                  <span key={lap.id} className={on ? 'tm-lap on' : 'tm-lap'} style={on ? { borderColor: colorOf(lap.id) } : undefined}>
                    <button type="button" aria-pressed={on} onClick={() => toggle(lap.id)} disabled={!on && picked.length >= MAX_LAPS}>
                      {on && <i style={{ background: colorOf(lap.id) }} aria-hidden="true" />}
                      {t('telemetryTool.lapShort', { number: lap.lap_number })}
                      <span className={lap.valid ? 'tm-time' : 'tm-time invalid'}>{formatLapTime(lap.lap_time_ms)}</span>
                      {lap.id === sessionBest?.id && <Icon name="trophy" small />}
                    </button>
                    {on && ready.length > 1 && (
                      <button
                        type="button"
                        className={lap.id === referenceId ? 'tm-ref on' : 'tm-ref'}
                        aria-pressed={lap.id === referenceId}
                        title={t('telemetryTool.setReference')}
                        aria-label={t('telemetryTool.setReferenceFor', { lap: lapName(lap, t) })}
                        onClick={() => setReference(lap.id)}
                      >
                        REF
                      </button>
                    )}
                  </span>
                )
              })}
            </div>
          </div>
        ))}
        <p className="muted tm-hint">{t('telemetryTool.pickHelp', { count: MAX_LAPS })}</p>
      </div>

      <div className="tm-toolbar">
        <div className="tm-channels" role="group" aria-label={t('telemetryTool.channels')}>
          {(['delta', ...CHANNELS] as Lane2[]).map((lane) => {
            const on = lanes.includes(lane)
            return (
              <button
                key={lane}
                type="button"
                className={on ? 'tm-toggle on' : 'tm-toggle'}
                aria-pressed={on}
                onClick={() =>
                  setLanes((old) =>
                    old.includes(lane)
                      ? old.filter((l) => l !== lane)
                      : (['delta', ...CHANNELS] as Lane2[]).filter((l) => l === lane || old.includes(l)),
                  )
                }
              >
                <Icon name={on ? 'check' : 'plus'} small />
                {laneDefs[lane].label}
              </button>
            )
          })}
        </div>
        <div className="tm-zoom">
          <button type="button" className="secondary small" onClick={() => zoom(0.6)} aria-label={t('telemetryTool.zoomIn')}>
            +
          </button>
          <button type="button" className="secondary small" onClick={() => zoom(1 / 0.6)} aria-label={t('telemetryTool.zoomOut')}>
            −
          </button>
          <button type="button" className="secondary small" onClick={() => setView(fullView)}>
            {t('telemetryTool.wholeLap')}
          </button>
        </div>
      </div>
      <p className="muted tm-hint">{t('telemetryTool.controls')}</p>

      {ready.length === 0 ? (
        <p className="muted">{picked.length === 0 ? t('telemetryTool.pickOne') : t('telemetryTool.loading')}</p>
      ) : (
        <div className="tm-body">
          <TelemetryChart
            x={x}
            xLabel={xLabel}
            lanes={chartLanes}
            series={series}
            view={currentView}
            onView={setView}
            cursor={cursor}
            onCursor={setCursor}
            overview={refGrid?.values.speed_kmh ?? gridLaps[0].values.speed_kmh}
          />
          <aside className="tm-side">
            {map && (
              <TelemetryMap
                map={map}
                view={[toS(currentView[0]), toS(currentView[1])]}
                cursor={cursor !== null ? grid[cursor] : null}
                fastest={fastest}
                colors={gridLaps.map((lap) => colorOf(lap.id))}
                onHover={(s) => setCursor(s === null ? null : Math.round(s * (grid.length - 1)))}
                onPick={(s) => {
                  const span = (fullView[1] - fullView[0]) * 0.08
                  const middle = length ? s * length : s * 100
                  const min = Math.min(Math.max(fullView[0], middle - span / 2), fullView[1] - span)
                  setView([min, min + span])
                }}
              />
            )}
            <Readout
              laps={ready}
              gridLaps={gridLaps}
              refGrid={refGrid}
              cursor={cursor}
              colorOf={colorOf}
              place={cursor !== null ? xLabel(x[cursor]) : null}
              referenceId={referenceId}
            />
          </aside>
        </div>
      )}
    </section>
  )
}

function lapName(lap: LapRow, t: (key: string, values?: Record<string, unknown>) => string) {
  return `${lap.driver_name} · ${t('telemetryTool.lapShort', { number: lap.lap_number })}`
}

/** The values of each picked lap at the cursor. */
function Readout({
  laps,
  gridLaps,
  refGrid,
  cursor,
  colorOf,
  place,
  referenceId,
}: {
  laps: LapRow[]
  gridLaps: GridLap[]
  refGrid: GridLap | null
  cursor: number | null
  colorOf: (id: number) => string
  place: string | null
  referenceId: number | null
}) {
  const { t } = useTranslation()
  const at = (values: (number | null)[], digits: number) =>
    cursor === null || values[cursor] === null || values[cursor] === undefined ? '—' : (values[cursor] as number).toFixed(digits)
  return (
    <div className="tm-readout">
      <p className="tm-readout-head">
        <b>{place ?? t('telemetryTool.hoverHelp')}</b>
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('telemetryTool.lap')}</th>
              <th scope="col" className="r">Δ</th>
              <th scope="col" className="r">km/h</th>
              <th scope="col" className="r">{t('telemetryTool.short.gas')}</th>
              <th scope="col" className="r">{t('telemetryTool.short.brake')}</th>
              <th scope="col" className="r">{t('telemetryTool.short.gear')}</th>
            </tr>
          </thead>
          <tbody>
            {laps.map((lap) => {
              const g = gridLaps.find((item) => item.id === lap.id)
              if (!g) return null
              const d = refGrid && lap.id !== referenceId ? delta(g, refGrid) : null
              const dv = d && cursor !== null ? d[cursor] : null
              return (
                <tr key={lap.id}>
                  <td>
                    <i className="tm-swatch" style={{ background: colorOf(lap.id) }} aria-hidden="true" />
                    <span className="tm-name" title={lap.driver_name}>
                      {lap.driver_name}
                    </span>{' '}
                    {t('telemetryTool.lapShort', { number: lap.lap_number })}
                    {lap.id === referenceId && <> · REF</>}
                  </td>
                  <td className={dv === null ? 'r' : dv > 0 ? 'r slower' : 'r faster'}>
                    {dv === null ? '—' : `${dv > 0 ? '+' : ''}${dv.toFixed(3)}`}
                  </td>
                  <td className="r">{at(g.values.speed_kmh, 0)}</td>
                  <td className="r">{at(g.values.gas, 0)}</td>
                  <td className="r">{at(g.values.brake, 0)}</td>
                  <td className="r">{at(g.values.gear, 0)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
