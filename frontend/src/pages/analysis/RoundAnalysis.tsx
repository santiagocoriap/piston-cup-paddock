import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { formatLapTime } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { TabEmpty } from '../TabEmpty'
import { BarChart, BoxChart, ChartCard, ChartGroup, DriverFilter, driverColor, HeatMap, LineChart, NeedsData, StackChart, type BoxRow, type LineSeries } from './charts'

type Analysis = components['schemas']['RoundAnalysisOut']
type Driver = components['schemas']['RoundDriverOut']
type Session = 'race' | 'qualifying' | 'practice'
type Measure = 'median' | 'mean' | 'trimmed'

const MIN_LAPS = 3
const seconds = (ms: number) => `${(ms / 1000).toFixed(3)} s`
const signedSeconds = (ms: number) => `${ms > 0 ? '+' : ''}${(ms / 1000).toFixed(3)} s`
const percent = (value: number) => `${value.toFixed(2)} %`

/** The data analysis tab of a round: the race on one side, and the laps on the other. */
export function RoundAnalysis({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const [view, setView] = useState<'race' | 'laps'>('race')
  const [session, setSession] = useState<Session>('race')
  const load = useLoad(
    () => api.GET('/api/rounds/{round_id}/analysis', { params: { path: { round_id: roundId }, query: { session } } }),
    [roundId, session],
  )
  const [hidden, setHidden] = useState<number[]>([])
  const data = load.data
  if (!data) return null
  if (data.sessions.length === 0) {
    return <TabEmpty heading={t('analysis.title')} icon="flag" title={t('tabEmpty.noLaps')} text={t('tabEmpty.laps')} />
  }
  const drivers = data.drivers.filter((d) => !hidden.includes(d.driver_id))
  return (
    <section aria-label={t('analysis.title')} className="analysis">
      <h2>{t('analysis.title')}</h2>
      <div className="tabs" role="tablist">
        {(['race', 'laps'] as const).map((name) => (
          <button key={name} type="button" role="tab" aria-selected={view === name} className={view === name ? 'active' : undefined} onClick={() => setView(name)}>
            {t(`analysis.views.${name}`)}
          </button>
        ))}
      </div>
      <div className="analysis-bar">
        <label>
          {t('analysis.session')}
          <select value={session} onChange={(event) => setSession(event.target.value as Session)}>
            {data.sessions.map((name) => (
              <option key={name} value={name}>
                {t(`laps.sessions.${name}`)}
              </option>
            ))}
          </select>
        </label>
        <DriverFilter drivers={data.drivers.map((d) => ({ id: d.driver_id, name: d.name }))} hidden={hidden} onChange={setHidden} />
      </div>
      {view === 'race' ? <RaceView data={data} drivers={drivers} /> : <LapsView data={data} drivers={drivers} />}
    </section>
  )
}

/** The laps of a driver as a line. A lap with an issue has a hollow point. */
function lapSeries(drivers: Driver[], value: (lap: Driver['laps'][number]) => number | null): LineSeries[] {
  return drivers.map((d) => ({
    key: d.driver_id,
    label: d.name,
    color: driverColor(d.driver_id),
    points: d.laps.map((lap) => ({ x: lap.number, y: value(lap), hollow: !lap.valid, mark: lap.contact })),
  }))
}

function RaceView({ data, drivers }: { data: Analysis; drivers: Driver[] }) {
  const { t } = useTranslation()
  const isRace = data.session === 'race'
  const notRace = isRace ? null : t('analysis.onlyRace')
  return (
    <>
      <ChartGroup title={t('analysis.groups.progression')} open>
        <PositionChart drivers={drivers} missing={notRace} />
        <GapChart drivers={drivers} missing={notRace} />
        <DuelChart drivers={drivers} missing={notRace} />
        <GainedChart drivers={drivers} missing={notRace} />
        <FirstLapChart drivers={drivers} missing={notRace} />
        <LeaderboardChart drivers={drivers} missing={notRace} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.pace')} open>
        <LapTimesChart drivers={drivers} />
        <PaceHeatMap drivers={drivers} />
        <DistributionChart drivers={drivers} />
        <PaceRanking drivers={drivers} />
        <ConsistencyChart drivers={drivers} />
        <TrendChart drivers={drivers} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.racecraft')}>
        <TrafficChart drivers={drivers} missing={notRace} />
        <ChangesChart drivers={drivers} missing={notRace} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.strategy')}>
        <StintChart drivers={drivers} hasPits={data.has_pit_data} />
      </ChartGroup>
      <NeedsData items={['overtakes', 'tyres', 'pitTime', 'fuel', 'undercut'].map((key) => t(`analysis.needs.${key}`))} />
    </>
  )
}

function PositionChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  return (
    <ChartCard
      title={t('analysis.position.title')}
      help={t('analysis.position.help')}
      missing={missing}
      csv={() => [['driver', 'lap', 'position'], ...drivers.flatMap((d) => d.laps.map((l) => [d.name, l.number, l.position]))]}
    >
      <LineChart series={lapSeries(drivers, (lap) => lap.position ?? null)} xLabel={t('analysis.lap')} yLabel={t('analysis.position.title')} invert integerY formatY={(v) => `P${v}`} />
    </ChartCard>
  )
}

function GapChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  return (
    <ChartCard
      title={t('analysis.gap.title')}
      help={t('analysis.gap.help')}
      missing={missing}
      csv={() => [['driver', 'lap', 'gap_ms'], ...drivers.flatMap((d) => d.laps.map((l) => [d.name, l.number, l.gap_to_leader_ms]))]}
    >
      <LineChart series={lapSeries(drivers, (lap) => (lap.gap_to_leader_ms === null || lap.gap_to_leader_ms === undefined ? null : lap.gap_to_leader_ms / 1000))} xLabel={t('analysis.lap')} yLabel={t('analysis.gap.title')} invert formatY={(v) => `+${v.toFixed(1)} s`} />
    </ChartCard>
  )
}

function DuelChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  const [first, setFirst] = useState<number | null>(null)
  const [second, setSecond] = useState<number | null>(null)
  const a = drivers.find((d) => d.driver_id === first) ?? drivers[0]
  const b = drivers.find((d) => d.driver_id === second) ?? drivers[1]
  const enough = !missing && a && b ? null : (missing ?? t('analysis.twoDrivers'))
  const total = (d: Driver, lap: number) => {
    const rows = d.laps.filter((l) => l.number <= lap)
    return rows.length === lap ? rows.reduce((sum, l) => sum + l.ms, 0) : null
  }
  const laps = a && b ? a.laps.map((lap) => lap.number).filter((lap) => total(b, lap) !== null) : []
  return (
    <ChartCard title={t('analysis.duel.title')} help={t('analysis.duel.help')} missing={enough} csv={() => [['lap', 'gap_ms'], ...laps.map((lap) => [lap, (total(b, lap) as number) - (total(a, lap) as number)])]}>
      {a && b && (
        <>
          <div className="chart-controls">
            <DriverSelect label="A" drivers={drivers} value={a.driver_id} onChange={setFirst} />
            <DriverSelect label="B" drivers={drivers} value={b.driver_id} onChange={setSecond} />
          </div>
          <LineChart
            series={[{ key: 'gap', label: `${b.name} − ${a.name}`, color: driverColor(b.driver_id), points: laps.map((lap) => ({ x: lap, y: ((total(b, lap) as number) - (total(a, lap) as number)) / 1000 })) }]}
            xLabel={t('analysis.lap')}
            yLabel={t('analysis.duel.title')}
            zero
            formatY={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)} s`}
          />
        </>
      )}
    </ChartCard>
  )
}

function DriverSelect({ label, drivers, value, onChange }: { label: string; drivers: { driver_id: number; name: string }[]; value: number; onChange: (id: number) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(Number(event.target.value))}>
        {drivers.map((d) => (
          <option key={d.driver_id} value={d.driver_id}>
            {d.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function GainedChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  const rows = drivers
    .filter((d) => d.grid && (d.finish || d.status))
    .map((d) => ({
      key: d.driver_id,
      label: d.name,
      value: d.finish ? (d.grid as number) - d.finish : null,
      color: driverColor(d.driver_id),
      note: d.status !== 'finished' ? t(`analysis.status.${d.status}`, { defaultValue: d.status ?? '' }) : `P${d.grid} → P${d.finish}`,
      muted: d.status !== 'finished',
    }))
    .sort((a, b) => (b.value ?? -99) - (a.value ?? -99))
  return (
    <ChartCard title={t('analysis.gained.title')} help={t('analysis.gained.help')} missing={missing ?? (rows.length === 0 ? t('analysis.noGrid') : null)} csv={() => [['driver', 'places'], ...rows.map((r) => [r.label, r.value])]}>
      <BarChart rows={rows} label={t('analysis.gained.title')} format={(v) => (v > 0 ? `+${v}` : String(v))} />
    </ChartCard>
  )
}

function FirstLapChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  const rows = drivers
    .filter((d) => d.grid && d.laps[0]?.position)
    .map((d) => ({ key: d.driver_id, label: d.name, value: (d.grid as number) - (d.laps[0].position as number), color: driverColor(d.driver_id), note: `P${d.grid} → P${d.laps[0].position}` }))
    .sort((a, b) => b.value - a.value)
  return (
    <ChartCard title={t('analysis.firstLap.title')} help={t('analysis.firstLap.help')} missing={missing ?? (rows.length === 0 ? t('analysis.noGrid') : null)} csv={() => [['driver', 'places'], ...rows.map((r) => [r.label, r.value])]}>
      <BarChart rows={rows} label={t('analysis.firstLap.title')} format={(v) => (v > 0 ? `+${v}` : String(v))} />
    </ChartCard>
  )
}

/** The classification at the end of a lap. Press the button to play the race lap by lap. */
function LeaderboardChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  const last = Math.max(1, ...drivers.flatMap((d) => d.laps.map((l) => l.number)))
  const [lap, setLap] = useState(1)
  const rows = drivers
    .map((d) => ({ d, at: d.laps.find((l) => l.number === Math.min(lap, last)) }))
    .filter((row) => row.at?.position)
    .sort((a, b) => (a.at!.position as number) - (b.at!.position as number))
  return (
    <ChartCard title={t('analysis.leaderboard.title')} help={t('analysis.leaderboard.help')} missing={missing}>
      <label className="chart-slider">
        {t('analysis.lapNumber', { number: Math.min(lap, last) })}
        <input type="range" min={1} max={last} value={Math.min(lap, last)} onChange={(event) => setLap(Number(event.target.value))} />
      </label>
      <BarChart
        rows={rows.map(({ d, at }) => ({ key: d.driver_id, label: `P${at!.position} ${d.name}`, value: (at!.gap_to_leader_ms ?? 0) / 1000, color: driverColor(d.driver_id) }))}
        label={t('analysis.leaderboard.title')}
        format={(v) => `+${v.toFixed(1)} s`}
      />
    </ChartCard>
  )
}

/** The slowest lap on the graph: the laps above it (a crash, a pit stop) stay on the top line. */
function limitOf(drivers: Driver[]): number | undefined {
  const clean = drivers.flatMap((d) => d.laps.filter((l) => l.clean).map((l) => l.ms)).sort((a, b) => a - b)
  return clean.length ? (clean[Math.floor(clean.length / 2)] * 1.1) / 1000 : undefined
}

function LapTimesChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const limit = limitOf(drivers)
  return (
    <ChartCard
      wide
      title={t('analysis.lapTimes.title')}
      help={t('analysis.lapTimes.help', { limit: limit ? formatLapTime(limit * 1000) : '—' })}
      csv={() => [['driver', 'lap', 'ms', 'valid', 'clean', 'pit', 'contact'], ...drivers.flatMap((d) => d.laps.map((l) => [d.name, l.number, l.ms, l.valid, l.clean, l.pit, l.contact]))]}
    >
      <LineChart series={lapSeries(drivers, (lap) => lap.ms / 1000)} xLabel={t('analysis.lap')} yLabel={t('analysis.lapTimes.title')} invert yLimit={limit} formatY={(v) => formatLapTime(v * 1000)} height={340} />
    </ChartCard>
  )
}

function PaceHeatMap({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const last = Math.max(0, ...drivers.flatMap((d) => d.laps.map((l) => l.number)))
  const columns = Array.from({ length: last }, (_, i) => String(i + 1))
  const best = Math.min(...drivers.flatMap((d) => d.laps.filter((l) => l.valid).map((l) => l.ms)))
  return (
    <ChartCard wide title={t('analysis.heat.title')} help={t('analysis.heat.help')} missing={last === 0 ? t('analysis.noLaps') : null}>
      <HeatMap
        label={t('analysis.heat.title')}
        columns={columns}
        low={0}
        high={8}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          cells: columns.map((_, index) => {
            const lap = d.laps.find((l) => l.number === index + 1)
            if (!lap) return { value: null }
            return {
              value: (lap.ms / best - 1) * 100,
              mark: lap.pit ? 'P' : lap.contact ? '!' : !lap.valid ? '×' : undefined,
              title: `${d.name} · ${t('analysis.lapNumber', { number: lap.number })} · ${formatLapTime(lap.ms)}`,
            }
          }),
        }))}
      />
    </ChartCard>
  )
}

const hasBox = (d: Driver) => d.spread.q1 !== null && d.spread.q1 !== undefined

function DistributionChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const rows: BoxRow[] = drivers
    .filter(hasBox)
    .sort((a, b) => (a.spread.median as number) - (b.spread.median as number))
    .map((d) => ({
      key: d.driver_id,
      label: d.name,
      color: driverColor(d.driver_id),
      q1: d.spread.q1 as number,
      q3: d.spread.q3 as number,
      median: d.spread.median as number,
      low: d.spread.low as number,
      high: d.spread.high as number,
      outliers: d.spread.outliers,
      note: `${formatLapTime(d.spread.median)} · n=${d.spread.count}`,
    }))
  return (
    <ChartCard title={t('analysis.distribution.title')} help={t('analysis.distribution.help')} missing={rows.length === 0 ? t('analysis.fewLaps', { count: MIN_LAPS }) : null} csv={() => [['driver', 'n', 'q1', 'median', 'q3'], ...drivers.map((d) => [d.name, d.spread.count, d.spread.q1, d.spread.median, d.spread.q3])]}>
      {rows.length > 0 && <BoxChart rows={rows} format={(v) => formatLapTime(v)} label={t('analysis.distribution.title')} />}
    </ChartCard>
  )
}

function PaceRanking({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const [measure, setMeasure] = useState<Measure>('median')
  const known = drivers.filter((d) => d.spread[measure] !== null && d.spread[measure] !== undefined)
  const best = Math.min(...known.map((d) => d.spread[measure] as number))
  const rows = [...known]
    .sort((a, b) => (a.spread[measure] as number) - (b.spread[measure] as number))
    .map((d) => {
      const value = d.spread[measure] as number
      return { key: d.driver_id, label: d.name, value: value - best, color: driverColor(d.driver_id), note: `${formatLapTime(value)} · ${percent((value / best - 1) * 100)}` }
    })
  return (
    <ChartCard title={t('analysis.ranking.title')} help={t('analysis.ranking.help')} missing={rows.length === 0 ? t('analysis.noLaps') : null} csv={() => [['driver', 'ms_behind'], ...rows.map((r) => [r.label, r.value])]}>
      <div className="chart-controls">
        <label>
          {t('analysis.ranking.measure')}
          <select value={measure} onChange={(event) => setMeasure(event.target.value as Measure)}>
            {(['median', 'mean', 'trimmed'] as const).map((name) => (
              <option key={name} value={name}>
                {t(`analysis.ranking.${name}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <BarChart rows={rows} label={t('analysis.ranking.title')} format={(v) => signedSeconds(v)} />
    </ChartCard>
  )
}

function ConsistencyChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const rows = drivers
    .filter((d) => d.spread.stdev !== null && d.spread.stdev !== undefined)
    .sort((a, b) => (a.spread.stdev as number) - (b.spread.stdev as number))
    .map((d) => ({ key: d.driver_id, label: d.name, value: d.spread.stdev as number, color: driverColor(d.driver_id), note: `MAD ${seconds(d.spread.mad as number)} · n=${d.spread.count}` }))
  return (
    <ChartCard title={t('analysis.consistency.title')} help={t('analysis.consistency.help')} missing={rows.length === 0 ? t('analysis.fewLaps', { count: MIN_LAPS }) : null} csv={() => [['driver', 'stdev_ms', 'mad_ms', 'n'], ...drivers.map((d) => [d.name, d.spread.stdev, d.spread.mad, d.spread.count])]}>
      <BarChart rows={rows} label={t('analysis.consistency.title')} format={seconds} />
    </ChartCard>
  )
}

/** The middle lap of the last clean laps. A window of 3 laps needs 3 clean laps. */
function rolling(laps: Driver['laps'], size: number) {
  return laps.map((lap, index) => {
    const part = laps.slice(0, index + 1).filter((l) => l.clean).slice(-size).map((l) => l.ms).sort((a, b) => a - b)
    return { x: lap.number, y: part.length === size && lap.clean ? part[Math.floor(size / 2)] / 1000 : null }
  })
}

function TrendChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const [size, setSize] = useState(3)
  const series = useMemo(() => drivers.map((d) => ({ key: d.driver_id, label: d.name, color: driverColor(d.driver_id), points: rolling(d.laps, size) })), [drivers, size])
  return (
    <ChartCard title={t('analysis.trend.title')} help={t('analysis.trend.help', { count: size })} missing={series.every((s) => s.points.every((p) => p.y === null)) ? t('analysis.fewLaps', { count: size }) : null}>
      <div className="chart-controls">
        <label>
          {t('analysis.trend.window')}
          <select value={size} onChange={(event) => setSize(Number(event.target.value))}>
            {[3, 5, 7].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      <LineChart series={series} xLabel={t('analysis.lap')} yLabel={t('analysis.trend.title')} invert formatY={(v) => formatLapTime(v * 1000)} />
    </ChartCard>
  )
}

function TrafficChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  const colors = { attacking: '#e10600', defending: '#facc15', clean_air: '#4ade80' }
  const kinds = ['attacking', 'defending', 'clean_air'] as const
  return (
    <ChartCard title={t('analysis.traffic.title')} help={t('analysis.traffic.help')} missing={missing} csv={() => [['driver', ...kinds], ...drivers.map((d) => [d.name, ...kinds.map((k) => d.battle?.[k] ?? 0)])]}>
      <StackChart
        share
        label={t('analysis.traffic.title')}
        legend={kinds.map((k) => ({ label: t(`analysis.traffic.${k}`), color: colors[k] }))}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          note: t('analysis.lapsCount', { count: d.laps.length }),
          parts: kinds.map((k) => ({ key: k, label: t(`analysis.traffic.${k}`), value: d.battle?.[k] ?? 0, color: colors[k] })),
        }))}
      />
    </ChartCard>
  )
}

function ChangesChart({ drivers, missing }: { drivers: Driver[]; missing: string | null }) {
  const { t } = useTranslation()
  const rows = drivers
    .map((d) => {
      let up = 0
      d.laps.forEach((lap, index) => {
        const before = d.laps[index - 1]?.position
        if (before && lap.position && lap.position < before) up += before - lap.position
      })
      return { key: d.driver_id, label: d.name, value: up, color: driverColor(d.driver_id) }
    })
    .sort((a, b) => b.value - a.value)
  return (
    <ChartCard title={t('analysis.changes.title')} help={t('analysis.changes.help')} missing={missing}>
      <BarChart rows={rows} label={t('analysis.changes.title')} />
    </ChartCard>
  )
}

const TYRE_COLORS = ['#e8e6e3', '#e5484d', '#f5c542', '#3fb27f', '#3b82f6', '#c084fc']

function StintChart({ drivers, hasPits }: { drivers: Driver[]; hasPits: boolean }) {
  const { t } = useTranslation()
  const tyres = [...new Set(drivers.flatMap((d) => d.laps.map((l) => l.tyre || '?')))]
  const color = (tyre: string) => TYRE_COLORS[tyres.indexOf(tyre) % TYRE_COLORS.length]
  const rows = drivers.map((d) => {
    const parts: { key: string; label: string; value: number; color: string }[] = []
    let pits = 0
    d.laps.forEach((lap) => {
      const tyre = lap.tyre || '?'
      const last = parts[parts.length - 1]
      if (lap.pit === 'out') pits += 1
      if (last && last.key === tyre && lap.pit !== 'out') last.value += 1
      else parts.push({ key: tyre, label: tyre, value: 1, color: color(tyre) })
    })
    return { key: d.driver_id, label: d.name, parts, note: hasPits ? t('analysis.stints.pits', { count: pits }) : t('analysis.lapsCount', { count: d.laps.length }) }
  })
  return (
    <ChartCard title={t('analysis.stints.title')} help={t(hasPits ? 'analysis.stints.help' : 'analysis.stints.noPits')} missing={tyres.length === 0 ? t('analysis.noLaps') : null}>
      <StackChart rows={rows} label={t('analysis.stints.title')} legend={tyres.map((tyre) => ({ label: tyre, color: color(tyre) }))} />
    </ChartCard>
  )
}

function LapsView({ data, drivers }: { data: Analysis; drivers: Driver[] }) {
  const { t } = useTranslation()
  return (
    <>
      <ChartGroup title={t('analysis.groups.lapSector')} open>
        <BestLapsChart drivers={drivers} />
        {data.has_sectors && <SectorsChart drivers={drivers} />}
        {data.has_sectors && <WaterfallChart drivers={drivers} />}
        {data.has_sectors && <TheoreticalChart drivers={drivers} />}
        {data.has_sectors && <SectorSpreadChart drivers={drivers} />}
        <ImprovementChart drivers={drivers} />
      </ChartGroup>
      <p className="muted">{t('analysis.telemetryTab')}</p>
      <NeedsData items={['gforce', 'tyreTemp', 'tyrePressure', 'wheelSlip', 'suspension', 'fuelLap'].map((key) => t(`analysis.needs.${key}`))} />
    </>
  )
}

function BestLapsChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const known = drivers.filter((d) => d.best_ms)
  const best = Math.min(...known.map((d) => d.best_ms as number))
  const rows = [...known]
    .sort((a, b) => (a.best_ms as number) - (b.best_ms as number))
    .map((d) => ({ key: d.driver_id, label: d.name, value: (d.best_ms as number) - best, color: driverColor(d.driver_id), note: `${formatLapTime(d.best_ms)} · ${t('analysis.lapNumber', { number: d.best_lap })}` }))
  return (
    <ChartCard title={t('analysis.bestLaps.title')} help={t('analysis.bestLaps.help')} missing={rows.length === 0 ? t('analysis.noLaps') : null} csv={() => [['driver', 'best_ms'], ...known.map((d) => [d.name, d.best_ms])]}>
      <BarChart rows={rows} label={t('analysis.bestLaps.title')} format={signedSeconds} />
    </ChartCard>
  )
}

function bestLapOf(d: Driver) {
  return d.laps.find((lap) => lap.number === d.best_lap)
}

function SectorsChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const count = Math.max(0, ...drivers.map((d) => d.best_sectors_ms.length))
  const best = Array.from({ length: count }, (_, i) => Math.min(...drivers.map((d) => d.best_sectors_ms[i] ?? Infinity)))
  return (
    <ChartCard title={t('analysis.sectors.title')} help={t('analysis.sectors.help')} missing={count === 0 ? t('analysis.noSectors') : null}>
      <HeatMap
        label={t('analysis.sectors.title')}
        columns={best.map((_, i) => `S${i + 1}`)}
        low={0}
        high={1000}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          cells: best.map((value, i) => {
            const mine = d.best_sectors_ms[i]
            return mine ? { value: mine - value, text: mine === value ? '★' : `+${((mine - value) / 1000).toFixed(2)}`, title: formatLapTime(mine) } : { value: null }
          }),
        }))}
      />
    </ChartCard>
  )
}

/** How each sector adds to the difference between the best laps of 2 drivers. */
function WaterfallChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const [first, setFirst] = useState<number | null>(null)
  const [second, setSecond] = useState<number | null>(null)
  const timed = drivers.filter((d) => bestLapOf(d)?.sectors_ms.length)
  const a = timed.find((d) => d.driver_id === first) ?? timed[0]
  const b = timed.find((d) => d.driver_id === second) ?? timed[1]
  if (!a || !b) return <ChartCard title={t('analysis.waterfall.title')} missing={t('analysis.twoDrivers')} />
  const sectorsA = bestLapOf(a)!.sectors_ms
  const sectorsB = bestLapOf(b)!.sectors_ms
  const diffs = sectorsA.map((value, index) => (sectorsB[index] ?? value) - value)
  const sum = (count: number) => diffs.slice(0, count).reduce((all, diff) => all + diff, 0)
  const total = sum(diffs.length)
  const rows = diffs.map((diff, index) => ({ key: index, label: `S${index + 1}`, value: diff, color: diff > 0 ? 'var(--danger)' : 'var(--pb)', note: `Σ ${signedSeconds(sum(index + 1))}` }))
  return (
    <ChartCard title={t('analysis.waterfall.title')} help={t('analysis.waterfall.help', { a: a.name, b: b.name })}>
      <div className="chart-controls">
        <DriverSelect label="A" drivers={timed} value={a.driver_id} onChange={setFirst} />
        <DriverSelect label="B" drivers={timed} value={b.driver_id} onChange={setSecond} />
      </div>
      <BarChart rows={[...rows, { key: 'total', label: t('analysis.waterfall.total'), value: total, color: 'var(--ink-3)' }]} label={t('analysis.waterfall.title')} format={signedSeconds} />
    </ChartCard>
  )
}

function TheoreticalChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const rows = drivers
    .filter((d) => d.theoretical_ms && d.best_ms)
    .sort((a, b) => (a.theoretical_ms as number) - (b.theoretical_ms as number))
    .map((d) => ({ key: d.driver_id, label: d.name, value: (d.best_ms as number) - (d.theoretical_ms as number), color: driverColor(d.driver_id), note: `${t('analysis.theoretical.short')} ${formatLapTime(d.theoretical_ms)} · ${t('analysis.theoretical.real')} ${formatLapTime(d.best_ms)}` }))
  return (
    <ChartCard title={t('analysis.theoretical.title')} help={t('analysis.theoretical.help')} missing={rows.length === 0 ? t('analysis.noSectors') : null}>
      <BarChart rows={rows} label={t('analysis.theoretical.title')} format={seconds} />
    </ChartCard>
  )
}

function quantile(sorted: number[], share: number) {
  const place = (sorted.length - 1) * share
  const low = Math.floor(place)
  return sorted[low] + (sorted[Math.min(low + 1, sorted.length - 1)] - sorted[low]) * (place - low)
}

function SectorSpreadChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<number | null>(null)
  const driver = drivers.find((d) => d.driver_id === picked) ?? drivers[0]
  const laps = driver?.laps.filter((l) => l.clean && l.sectors_ms.length) ?? []
  const count = Math.max(0, ...laps.map((l) => l.sectors_ms.length))
  const rows: BoxRow[] = Array.from({ length: count }, (_, index) => {
    const sorted = laps.map((l) => l.sectors_ms[index]).filter(Boolean).sort((a, b) => a - b)
    return {
      key: index,
      label: `S${index + 1}`,
      color: driverColor(driver.driver_id),
      // Each sector on its own scale would hide the spread: the values are from the sector best.
      q1: quantile(sorted, 0.25) - sorted[0],
      q3: quantile(sorted, 0.75) - sorted[0],
      median: quantile(sorted, 0.5) - sorted[0],
      low: 0,
      high: sorted[sorted.length - 1] - sorted[0],
      outliers: [],
      note: `${t('analysis.sectorSpread.best')} ${formatLapTime(sorted[0])}`,
    }
  })
  return (
    <ChartCard title={t('analysis.sectorSpread.title')} help={t('analysis.sectorSpread.help')} missing={laps.length < MIN_LAPS ? t('analysis.fewLaps', { count: MIN_LAPS }) : null}>
      {driver && (
        <div className="chart-controls">
          <DriverSelect label={t('analysis.driver')} drivers={drivers} value={driver.driver_id} onChange={setPicked} />
        </div>
      )}
      <BoxChart rows={rows} format={(v) => `+${(v / 1000).toFixed(2)} s`} label={t('analysis.sectorSpread.title')} />
    </ChartCard>
  )
}

/** The best valid lap of each driver after each lap: the line steps down at a new personal best. */
function ImprovementChart({ drivers }: { drivers: Driver[] }) {
  const { t } = useTranslation()
  const series = drivers.map((d) => {
    let best: number | null = null
    return {
      key: d.driver_id,
      label: d.name,
      color: driverColor(d.driver_id),
      points: d.laps.map((lap) => {
        const improved = lap.valid && (best === null || lap.ms < best)
        if (improved) best = lap.ms
        return { x: lap.number, y: best === null ? null : best / 1000, mark: improved }
      }),
    }
  })
  return (
    <ChartCard title={t('analysis.improvement.title')} help={t('analysis.improvement.help')} missing={series.every((s) => s.points.every((p) => p.y === null)) ? t('analysis.noLaps') : null}>
      <LineChart series={series} step invert xLabel={t('analysis.lap')} yLabel={t('analysis.improvement.title')} formatY={(v) => formatLapTime(v * 1000)} />
    </ChartCard>
  )
}
