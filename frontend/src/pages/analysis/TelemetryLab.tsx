import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { formatLapTime } from '../../lib/format'
import { fit, polyline, trackOutline } from '../../lib/trackMap'
import { unwrap } from '../../lib/telemetryMath'
import { useLoad } from '../../lib/useLoad'
import { BarChart, ChartCard, ChartGroup, HeatMap, LineChart, ScatterChart, type LineSeries } from './charts'

type LapRow = components['schemas']['LapOut']
type LapDetail = components['schemas']['LapDetailOut']

const COLORS = ['#e10600', '#38bdf8', '#facc15']
const MAX_LAPS = COLORS.length
const POINTS = 400
const WHEELS = ['fl', 'fr', 'rl', 'rr'] as const
const WHEEL_COLORS = ['#38bdf8', '#4ade80', '#facc15', '#e10600']
const PARTS = 20
/** The channels that the correlation graph can compare. */
const AXES = ['speed_kmh', 'gas', 'brake', 'steer', 'rpm', 'g_lat', 'g_long'] as const
type Axis = (typeof AXES)[number]

/** Every n-th sample, so a graph stays fast. */
function thin<T>(values: T[], count: number): T[] {
  const step = Math.max(1, Math.floor(values.length / count))
  return values.filter((_, index) => index % step === 0)
}

/** The channel of a lap against the place on the lap, in percent. The "v_" channels have their
 * own times, because the script sends them less often. */
function line(lap: LapDetail, channel: string, scale = 1): { x: number; y: number | null }[] {
  const vehicle = channel.startsWith('v_')
  const places = lap.channels[vehicle ? 'v_pos' : 'pos']
  const values = lap.channels[channel]
  if (!places || !values) return []
  const distance = unwrap(places)
  const points = distance.map((place, index) => ({ x: Math.round(place * 10000) / 100, y: values[index] * scale })).filter((p) => p.x >= 0 && p.x <= 100)
  return thin(points, POINTS)
}

function has(laps: LapDetail[], channel: string) {
  return laps.some((lap) => (lap.channels[channel]?.length ?? 0) > 0)
}

/** Graphs from the telemetry of the laps that the user picks: forces, tyres, suspension, and the
 * racing line. A lap from before these channels existed has no values for these graphs. */
export function TelemetryLab({ roundId, session }: { roundId: number; session: string }) {
  const { t } = useTranslation()
  const rows = useLoad(() => api.GET('/api/rounds/{round_id}/telemetry', { params: { path: { round_id: roundId } } }), [roundId])
  const map = useLoad(() => api.GET('/api/rounds/{round_id}/track-map', { params: { path: { round_id: roundId } } }), [roundId])
  const inSession = useMemo(() => (rows.data ?? []).filter((lap) => lap.session_type === session && lap.access === 'full'), [rows.data, session])
  const [picked, setPicked] = useState<number[]>([])
  const [details, setDetails] = useState<Record<number, LapDetail>>({})
  const chosen = picked.filter((id) => inSession.some((lap) => lap.id === id))

  useEffect(() => {
    const missing = chosen.filter((id) => !details[id])
    if (missing.length === 0) return
    let stop = false
    Promise.all(missing.map((id) => api.GET('/api/telemetry-laps/{lap_id}', { params: { path: { lap_id: id } } }))).then((answers) => {
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
    // The list of picked laps is a new array on each render, so its text is the dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen.join(','), details])

  const laps = chosen.map((id) => details[id]).filter((lap): lap is LapDetail => !!lap)
  const name = (lap: LapDetail) => `${lap.driver_name} · ${t('analysis.lapNumber', { number: lap.lap_number })}`
  const color = (lap: LapDetail) => COLORS[chosen.indexOf(lap.id) % COLORS.length]
  const series = (channel: string, scale = 1): LineSeries[] => laps.map((lap) => ({ key: lap.id, label: name(lap), color: color(lap), points: line(lap, channel, scale) }))
  const wheels = (kind: string, lap: LapDetail | undefined): LineSeries[] =>
    lap ? WHEELS.map((wheel, index) => ({ key: wheel, label: t(`analysis.lab.wheels.${wheel}`), color: WHEEL_COLORS[index], points: line(lap, `v_${kind}_${wheel}`) })) : []
  const first = laps[0]
  const place = t('analysis.lab.place')
  const percent = (v: number) => `${Math.round(v)} %`
  const noData = t('analysis.lab.noData')

  return (
    <ChartGroup title={t('analysis.groups.lab')}>
      <div className="chart-wide analysis-lab-pick">
        <label>
          {t('analysis.lab.pick', { count: MAX_LAPS })}
          <select
            multiple
            size={Math.min(8, Math.max(3, inSession.length))}
            value={chosen.map(String)}
            onChange={(event) => setPicked([...event.target.selectedOptions].map((o) => Number(o.value)).slice(0, MAX_LAPS))}
          >
            {inSession.map((lap: LapRow) => (
              <option key={lap.id} value={lap.id}>
                {lap.driver_name} · {t('analysis.lapNumber', { number: lap.lap_number })} · {formatLapTime(lap.lap_time_ms)}
              </option>
            ))}
          </select>
        </label>
        {inSession.length === 0 && <p className="muted">{t('analysis.lab.noLaps')}</p>}
      </div>
      {laps.length > 0 && (
        <>
          <ChartCard title={t('analysis.lab.gLong')} help={t('analysis.lab.gLongHelp')} missing={has(laps, 'g_long') ? null : noData}>
            <LineChart series={series('g_long')} xLabel={place} yLabel={t('analysis.lab.gLong')} zero formatX={percent} formatY={(v) => `${v.toFixed(1)} G`} />
          </ChartCard>
          <ChartCard title={t('analysis.lab.gLat')} help={t('analysis.lab.gLatHelp')} missing={has(laps, 'g_lat') ? null : noData}>
            <LineChart series={series('g_lat')} xLabel={place} yLabel={t('analysis.lab.gLat')} zero formatX={percent} formatY={(v) => `${v.toFixed(1)} G`} />
          </ChartCard>
          <GgChart laps={laps} color={color} />
          <RacingLine laps={laps} color={color} name={name} map={map.data ?? null} />
          <TyreHeat lap={first} name={first ? name(first) : ''} />
          <ChartCard title={t('analysis.lab.pressure')} help={t('analysis.lab.oneLap', { lap: first ? name(first) : '' })} missing={has(laps, 'v_pressure_fl') ? null : noData}>
            <LineChart series={wheels('pressure', first)} xLabel={place} yLabel={t('analysis.lab.pressure')} formatX={percent} formatY={(v) => `${v.toFixed(1)} psi`} />
          </ChartCard>
          <ChartCard title={t('analysis.lab.slip')} help={t('analysis.lab.slipHelp')} missing={has(laps, 'v_slip_fl') ? null : noData}>
            <LineChart series={wheels('slip', first)} xLabel={place} yLabel={t('analysis.lab.slip')} formatX={percent} />
          </ChartCard>
          <ChartCard title={t('analysis.lab.suspension')} help={t('analysis.lab.oneLap', { lap: first ? name(first) : '' })} missing={has(laps, 'v_susp_fl') ? null : noData}>
            <LineChart series={wheels('susp', first)} xLabel={place} yLabel={t('analysis.lab.suspension')} formatX={percent} formatY={(v) => `${(v * 1000).toFixed(0)} mm`} />
          </ChartCard>
          <Smoothness laps={laps} name={name} color={color} />
          <Correlation laps={laps} color={color} />
          <CornerExit laps={laps} color={color} name={name} />
        </>
      )}
    </ChartGroup>
  )
}

function GgChart({ laps, color }: { laps: LapDetail[]; color: (lap: LapDetail) => string }) {
  const { t } = useTranslation()
  const points = laps.flatMap((lap) => {
    const [x, y] = [lap.channels.g_lat ?? [], lap.channels.g_long ?? []]
    return thin(x.map((value, index) => ({ key: `${lap.id}-${index}`, label: '', x: value, y: y[index], color: color(lap) })), 1200)
  })
  return (
    <ChartCard title={t('analysis.lab.gg')} help={t('analysis.lab.ggHelp')} missing={points.length ? null : t('analysis.lab.noData')}>
      <ScatterChart points={points} labels={false} xLabel={t('analysis.lab.gLat')} yLabel={t('analysis.lab.gLong')} formatX={(v) => v.toFixed(1)} formatY={(v) => v.toFixed(1)} />
    </ChartCard>
  )
}

function RacingLine({ laps, color, name, map }: { laps: LapDetail[]; color: (lap: LapDetail) => string; name: (lap: LapDetail) => string; map: { x: number[]; z: number[] } | null }) {
  const { t } = useTranslation()
  const size = 460
  const trails = laps
    .filter((lap) => lap.channels.x?.length)
    .map((lap) => ({ lap, points: thin(lap.channels.x.map((x, index) => ({ x, z: lap.channels.z[index] })), 1000) }))
  const outline = trackOutline(map, [])
  const place = fit([...outline, ...trails.flatMap((trail) => trail.points)], size, 12)
  return (
    <ChartCard title={t('analysis.lab.line')} help={t('analysis.lab.lineHelp')} missing={trails.length ? null : t('analysis.lab.noData')}>
      <svg className="chart chart-map" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={t('analysis.lab.line')}>
        {outline.length > 0 && <polyline points={polyline(outline, place)} fill="none" stroke="var(--line-strong)" strokeWidth={7} strokeLinejoin="round" />}
        {trails.map((trail) => (
          <polyline key={trail.lap.id} points={polyline(trail.points, place)} fill="none" stroke={color(trail.lap)} strokeWidth={1.2}>
            <title>{name(trail.lap)}</title>
          </polyline>
        ))}
      </svg>
    </ChartCard>
  )
}

function TyreHeat({ lap, name }: { lap: LapDetail | undefined; name: string }) {
  const { t } = useTranslation()
  const places = lap?.channels.v_pos
  if (!lap || !places) return <ChartCard title={t('analysis.lab.temps')} missing={t('analysis.lab.noData')} />
  const rows = WHEELS.flatMap((wheel) =>
    (['in', 'mid', 'out'] as const).map((zone) => {
      const values = lap.channels[`v_temp_${zone}_${wheel}`] ?? []
      return {
        key: `${wheel}-${zone}`,
        label: `${t(`analysis.lab.wheels.${wheel}`)} · ${t(`analysis.lab.zones.${zone}`)}`,
        cells: Array.from({ length: PARTS }, (_, part) => {
          const inside = values.filter((_, i) => Math.floor(places[i] * PARTS) === part)
          const mean = inside.length ? inside.reduce((a, b) => a + b, 0) / inside.length : null
          return mean === null ? { value: null } : { value: mean, title: `${Math.round(mean)} °C` }
        }),
      }
    }),
  )
  return (
    <ChartCard wide title={t('analysis.lab.temps')} help={t('analysis.lab.tempsHelp', { lap: name })}>
      <HeatMap rows={rows} columns={Array.from({ length: PARTS }, (_, part) => `${part * 5}`)} label={t('analysis.lab.temps')} reverse={false} />
    </ChartCard>
  )
}

/** A smooth driver turns the wheel with small changes: the mean change for each sample. */
function Smoothness({ laps, name, color }: { laps: LapDetail[]; name: (lap: LapDetail) => string; color: (lap: LapDetail) => string }) {
  const { t } = useTranslation()
  const rows = laps
    .filter((lap) => (lap.channels.steer?.length ?? 0) > 1)
    .map((lap) => {
      const steer = lap.channels.steer
      const total = steer.slice(1).reduce((sum, value, index) => sum + Math.abs(value - steer[index]), 0)
      return { key: lap.id, label: name(lap), value: total / (steer.length - 1), color: color(lap) }
    })
    .sort((a, b) => a.value - b.value)
  return (
    <ChartCard title={t('analysis.lab.smooth')} help={t('analysis.lab.smoothHelp')}>
      <BarChart rows={rows} label={t('analysis.lab.smooth')} format={(v) => `${v.toFixed(2)}°`} />
    </ChartCard>
  )
}

/** The corners of a lap: each low point of the speed, with at least DROP km/h on each side. */
const DROP = 15
const EXIT_SAMPLES = 40 // 2 seconds at 20 samples each second.
const LATER_SAMPLES = 100 // 5 seconds.

export function cornerExits(speed: number[]): { exit: number; later: number }[] {
  const found: { exit: number; later: number }[] = []
  let low = 0
  let high = 0
  for (let i = 1; i < speed.length; i++) {
    if (speed[i] < speed[low]) low = i
    if (speed[i] > speed[high]) high = i
    if (speed[high] - speed[low] >= DROP && high < low && speed[i] - speed[low] >= DROP) {
      if (low + LATER_SAMPLES < speed.length) found.push({ exit: speed[low + EXIT_SAMPLES], later: speed[low + LATER_SAMPLES] })
      high = i
      low = i
    } else if (high > low) {
      low = high
    }
  }
  return found
}

function CornerExit({ laps, color, name }: { laps: LapDetail[]; color: (lap: LapDetail) => string; name: (lap: LapDetail) => string }) {
  const { t } = useTranslation()
  const points = laps.flatMap((lap) =>
    cornerExits(lap.channels.speed_kmh ?? []).map((corner, index) => ({ key: `${lap.id}-${index}`, label: `${index + 1}`, x: corner.exit, y: corner.later, color: color(lap) })),
  )
  return (
    <ChartCard title={t('analysis.lab.exit')} help={t('analysis.lab.exitHelp', { laps: laps.map(name).join(' · ') })} missing={points.length === 0 ? t('analysis.noLaps') : null}>
      <ScatterChart points={points} xLabel={t('analysis.lab.exitX')} yLabel={t('analysis.lab.exitY')} formatX={(v) => String(Math.round(v))} formatY={(v) => String(Math.round(v))} />
    </ChartCard>
  )
}

function Correlation({ laps, color }: { laps: LapDetail[]; color: (lap: LapDetail) => string }) {
  const { t } = useTranslation()
  const [xName, setX] = useState<Axis>('speed_kmh')
  const [yName, setY] = useState<Axis>('g_long')
  const points = laps.flatMap((lap) => {
    const [x, y] = [lap.channels[xName] ?? [], lap.channels[yName] ?? []]
    return thin(x.map((value, index) => ({ key: `${lap.id}-${index}`, label: '', x: value, y: y[index], color: color(lap) })), 800)
  })
  const label = (axis: Axis) => t(`analysis.lab.axes.${axis}`)
  return (
    <ChartCard title={t('analysis.lab.correlation')} help={t('analysis.lab.correlationHelp')} missing={points.length ? null : t('analysis.lab.noData')}>
      <div className="chart-controls">
        {([['X', xName, setX], ['Y', yName, setY]] as const).map(([name, value, set]) => (
          <label key={name}>
            {name}
            <select value={value} onChange={(event) => set(event.target.value as Axis)}>
              {AXES.map((axis) => (
                <option key={axis} value={axis}>
                  {label(axis)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <ScatterChart points={points} labels={false} xLabel={label(xName)} yLabel={label(yName)} formatX={(v) => String(Math.round(v * 10) / 10)} formatY={(v) => String(Math.round(v * 10) / 10)} />
    </ChartCard>
  )
}
