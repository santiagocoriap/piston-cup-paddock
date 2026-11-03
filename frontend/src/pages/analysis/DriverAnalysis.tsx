import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { formatLapTime } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { BarChart, ChartCard, ChartGroup, driverColor, HeatMap, LineChart, RadarChart, ScatterChart, StackChart, type LineSeries } from './charts'
import { forecastSeries, type Season, type SeasonDriver } from './SeasonAnalysis'

type Cell = SeasonDriver['cells'][number]

const RADAR = ['pace', 'consistency', 'qualifying', 'results', 'racecraft', 'reliability'] as const
const FEW = 2
const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null)

/** The rounds of a driver with a result, in the order of the calendar. */
const raced = (driver: SeasonDriver) => driver.cells.filter((c) => c.status)

/** The data analysis section of a driver page: one season at a time, with an optional rival. */
export function DriverAnalysis({ driverId }: { driverId: number }) {
  const { t } = useTranslation()
  const load = useLoad(() => api.GET('/api/drivers/{driver_id}/analysis', { params: { path: { driver_id: driverId } } }), [driverId])
  const [seasonId, setSeasonId] = useState<number | null>(null)
  const [rivalId, setRivalId] = useState<number | null>(null)
  const seasons = (load.data ?? []).filter((s) => s.drivers.some((d) => d.driver_id === driverId && raced(d).length > 0))
  const season = seasons.find((s) => s.season_id === seasonId) ?? seasons[0]
  if (!load.data) return null
  if (!season) {
    return (
      <section aria-labelledby="driver-analysis">
        <h2 id="driver-analysis">{t('analysis.title')}</h2>
        <p className="muted">{t('analysis.noDriverResults')}</p>
      </section>
    )
  }
  const me = season.drivers.find((d) => d.driver_id === driverId) as SeasonDriver
  const others = season.drivers.filter((d) => d.driver_id !== driverId)
  const rival = others.find((d) => d.driver_id === rivalId) ?? others[0] ?? null
  return (
    <section aria-labelledby="driver-analysis" className="analysis">
      <h2 id="driver-analysis">{t('analysis.title')}</h2>
      <div className="analysis-bar">
        <label>
          {t('analysis.season')}
          <select value={season.season_id} onChange={(event) => setSeasonId(Number(event.target.value))}>
            {seasons.map((s) => (
              <option key={s.season_id} value={s.season_id}>
                {s.championship_name} · {s.season_name}
              </option>
            ))}
          </select>
        </label>
        {rival && (
          <label>
            {t('analysis.rival')}
            <select value={rival.driver_id} onChange={(event) => setRivalId(Number(event.target.value))}>
              {others.map((d) => (
                <option key={d.driver_id} value={d.driver_id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <ChartGroup title={t('analysis.groups.overview')} open>
        <RadarCard me={me} rival={rival} />
        <PaceConsistency season={season} me={me} />
        <FormChart me={me} />
        <EloChart me={me} rival={rival} />
        <EvolutionChart me={me} />
        <CircuitTypes season={season} me={me} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.qualifyingRace')}>
        <GridFinish me={me} />
        <QualifyingHistory me={me} />
        <PaceHistory me={me} />
        <FinishHistogram me={me} />
        <GainedPerRace me={me} />
        <BestVsTypical me={me} />
        <ConsistencyByRace me={me} />
        <ExpectedActual season={season} me={me} />
      </ChartGroup>
      {rival && (
        <ChartGroup title={t('analysis.groups.headToHead')}>
          <HeadToHead me={me} rival={rival} />
          <PointsDuel me={me} rival={rival} />
          <PaceDuel me={me} rival={rival} />
          <SectorDuel me={me} rival={rival} />
          <RivalryHistory me={me} rival={rival} />
        </ChartGroup>
      )}
      <ChartGroup title={t('analysis.groups.reliability')}>
        <Reliability me={me} />
        <OvertakesByRace season={season} me={me} />
        <BattlesByRace me={me} />
        <IncidentsByRace me={me} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.advanced')}>
        <Forecast me={me} />
        <Decomposition me={me} />
        <Similarity season={season} me={me} />
        <TrackHistory seasons={seasons} driverId={driverId} />
      </ChartGroup>
    </section>
  )
}

function RadarCard({ me, rival }: { me: SeasonDriver; rival: SeasonDriver | null }) {
  const { t } = useTranslation()
  const axes = RADAR.map((key) => t(`analysis.radar.${key}`))
  const has = RADAR.some((key) => me.scores[key] !== null && me.scores[key] !== undefined)
  return (
    <ChartCard title={t('analysis.radar.title')} help={t('analysis.radar.help')} missing={has ? null : t('analysis.radar.few')}>
      <RadarChart
        axes={axes}
        label={t('analysis.radar.title')}
        series={[
          { key: me.driver_id, label: me.name, color: driverColor(me.driver_id), values: RADAR.map((key) => me.scores[key] ?? null) },
          ...(rival ? [{ key: rival.driver_id, label: rival.name, color: driverColor(rival.driver_id), values: RADAR.map((key) => rival.scores[key] ?? null), dashed: true }] : []),
        ]}
      />
    </ChartCard>
  )
}

function PaceConsistency({ season, me }: { season: Season; me: SeasonDriver }) {
  const { t } = useTranslation()
  const points = season.drivers
    .filter((d) => d.average_pace_pct !== null && d.average_pace_pct !== undefined && d.average_stdev_ms !== null && d.average_stdev_ms !== undefined)
    .map((d) => ({ key: d.driver_id, label: d.name, x: d.average_pace_pct as number, y: (d.average_stdev_ms as number) / 1000, color: driverColor(d.driver_id), strong: d.driver_id === me.driver_id }))
  return (
    <ChartCard title={t('analysis.paceConsistency.title')} help={t('analysis.paceConsistency.help')} missing={points.length < 2 ? t('analysis.noLaps') : null}>
      <ScatterChart points={points} xLabel={t('analysis.paceConsistency.x')} yLabel={t('analysis.paceConsistency.y')} formatX={(v) => `+${v.toFixed(2)} %`} formatY={(v) => `${v.toFixed(2)} s`} />
    </ChartCard>
  )
}

function FormChart({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const [size, setSize] = useState(3)
  const rows = raced(me)
  const series: LineSeries[] = [
    { key: 'finish', label: t('analysis.form.finish'), color: driverColor(me.driver_id), points: rows.map((c) => ({ x: c.number, y: c.finish ?? null })) },
    {
      key: 'rolling',
      label: t('analysis.form.rolling', { count: size }),
      color: 'var(--ink-2)',
      dashed: true,
      points: rows.map((c, index) => {
        const part = rows.slice(Math.max(0, index - size + 1), index + 1).map((r) => r.finish).filter((f): f is number => !!f)
        return { x: c.number, y: part.length === size ? mean(part) : null }
      }),
    },
  ]
  return (
    <ChartCard title={t('analysis.form.title')} help={t('analysis.form.help')} missing={rows.length < FEW ? t('analysis.fewRounds', { count: FEW }) : null}>
      <div className="chart-controls">
        <label>
          {t('analysis.trend.window')}
          <select value={size} onChange={(event) => setSize(Number(event.target.value))}>
            {[2, 3, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      <LineChart series={series} xLabel={t('analysis.round')} yLabel={t('analysis.form.title')} invert integerY formatY={(v) => `P${Math.round(v * 10) / 10}`} />
    </ChartCard>
  )
}

function EloChart({ me, rival }: { me: SeasonDriver; rival: SeasonDriver | null }) {
  const { t } = useTranslation()
  const line = (d: SeasonDriver): LineSeries => ({ key: d.driver_id, label: d.name, color: driverColor(d.driver_id), points: d.cells.filter((c) => c.elo !== null && c.elo !== undefined).map((c) => ({ x: c.number, y: c.elo as number })) })
  const series = [line(me), ...(rival ? [line(rival)] : [])]
  return (
    <ChartCard title={t('analysis.elo.title')} help={t('analysis.elo.help')} missing={series[0].points.length === 0 ? t('analysis.fewRounds', { count: 1 }) : null}>
      <LineChart series={series} xLabel={t('analysis.round')} yLabel={t('analysis.elo.title')} formatY={(v) => String(Math.round(v))} />
    </ChartCard>
  )
}

function EvolutionChart({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = raced(me)
  const series: LineSeries[] = [
    { key: 'race', label: t('analysis.evolution.race'), color: driverColor(me.driver_id), points: rows.map((c) => ({ x: c.number, y: c.pace_pct ?? null })) },
    { key: 'qualifying', label: t('analysis.evolution.qualifying'), color: 'var(--ink-2)', dashed: true, points: rows.map((c) => ({ x: c.number, y: c.qualifying_pct ?? null })) },
  ]
  return (
    <ChartCard title={t('analysis.evolution.title')} help={t('analysis.evolution.help')} missing={rows.length < FEW ? t('analysis.fewRounds', { count: FEW }) : null}>
      <LineChart series={series} xLabel={t('analysis.round')} yLabel={t('analysis.evolution.title')} invert formatY={(v) => `+${v.toFixed(2)} %`} />
    </ChartCard>
  )
}

function CircuitTypes({ season, me }: { season: Season; me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = (['high_speed', 'mixed', 'technical'] as const).flatMap((kind) => {
    const numbers = season.rounds.filter((r) => r.circuit_type === kind).map((r) => r.number)
    const values = me.cells.filter((c) => numbers.includes(c.number) && c.pace_pct !== null && c.pace_pct !== undefined).map((c) => c.pace_pct as number)
    const value = mean(values)
    return value === null ? [] : [{ key: kind, label: t(`analysis.circuitType.${kind}`), value, color: driverColor(me.driver_id), note: `n=${values.length}` }]
  })
  return (
    <ChartCard title={t('analysis.circuitType.title')} help={t('analysis.circuitType.help')} missing={rows.length === 0 ? t('analysis.circuitType.none') : null}>
      <BarChart rows={rows} label={t('analysis.circuitType.title')} format={(v) => `+${v.toFixed(2)} %`} />
    </ChartCard>
  )
}

function ConsistencyByRace({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.stdev_ms !== null && c.stdev_ms !== undefined)
  return (
    <ChartCard title={t('analysis.consistencyByRace.title')} help={t('analysis.consistency.help')} missing={rows.length === 0 ? t('analysis.noLaps') : null}>
      <BarChart rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: (c.stdev_ms as number) / 1000, color: driverColor(me.driver_id) }))} label={t('analysis.consistencyByRace.title')} format={(v) => `${v.toFixed(3)} s`} />
    </ChartCard>
  )
}

/** The expected finish is the start position. So a point above the line is a race with places won. */
function ExpectedActual({ season, me }: { season: Season; me: SeasonDriver }) {
  const { t } = useTranslation()
  void season
  const points = me.cells.filter((c) => c.grid && c.finish).map((c) => ({ key: c.number, label: `${c.number}`, x: c.grid as number, y: c.finish as number, color: driverColor(me.driver_id) }))
  return (
    <ChartCard title={t('analysis.expected.title')} help={t('analysis.expected.help')} missing={points.length === 0 ? t('analysis.noGrid') : null}>
      <ScatterChart points={points} diagonal invertY xLabel={t('analysis.expected.x')} yLabel={t('analysis.expected.y')} formatX={(v) => `P${Math.round(v)}`} formatY={(v) => `P${Math.round(v)}`} />
    </ChartCard>
  )
}

function SectorDuel({ me, rival }: { me: SeasonDriver; rival: SeasonDriver }) {
  const { t } = useTranslation()
  const rounds = shared(me, rival).filter(([a, b]) => a.sectors_ms.length && b.sectors_ms.length)
  const count = Math.max(0, ...rounds.map(([a]) => a.sectors_ms.length))
  return (
    <ChartCard title={t('analysis.sectorDuel.title')} help={t('analysis.sectorDuel.help', { a: me.name, b: rival.name })} missing={rounds.length === 0 ? t('analysis.noSectorsShared') : null}>
      <HeatMap
        label={t('analysis.sectorDuel.title')}
        columns={Array.from({ length: count }, (_, i) => `S${i + 1}`)}
        low={-500}
        high={500}
        rows={rounds.map(([a, b]) => ({
          key: a.number,
          label: `${a.number} · ${a.track}`,
          cells: Array.from({ length: count }, (_, i) => {
            const [mine, theirs] = [a.sectors_ms[i], b.sectors_ms[i]]
            if (!mine || !theirs) return { value: null }
            const gap = mine - theirs
            return { value: gap, text: `${gap > 0 ? '+' : ''}${(gap / 1000).toFixed(2)}` }
          }),
        }))}
      />
    </ChartCard>
  )
}

function RivalryHistory({ me, rival }: { me: SeasonDriver; rival: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = shared(me, rival).filter(([a, b]) => a.finish && b.finish)
  return (
    <ChartCard title={t('analysis.rivalryHistory.title')} help={t('analysis.rivalryHistory.help', { a: me.name, b: rival.name })} missing={rows.length === 0 ? t('analysis.noShared') : null}>
      <BarChart
        rows={rows.map(([a, b]) => {
          const value = (b.finish as number) - (a.finish as number)
          return { key: a.number, label: `${a.number} · ${a.track}`, value, color: driverColor(value >= 0 ? me.driver_id : rival.driver_id), note: `P${a.finish} / P${b.finish}` }
        })}
        label={t('analysis.rivalryHistory.title')}
        format={(v) => (v > 0 ? `+${v}` : String(v))}
      />
    </ChartCard>
  )
}

function OvertakesByRace({ season, me }: { season: Season; me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.overtakes !== null && c.overtakes !== undefined)
  const average = (number: number) => mean(season.drivers.flatMap((d) => d.cells.filter((c) => c.number === number && c.overtakes !== null && c.overtakes !== undefined).map((c) => c.overtakes as number)))
  return (
    <ChartCard title={t('analysis.overtakes.title')} help={t('analysis.overtakes.help')} missing={rows.length === 0 ? t('analysis.noPositions') : null}>
      <BarChart rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: c.overtakes as number, color: driverColor(me.driver_id), note: t('analysis.overtakes.field', { value: (average(c.number) ?? 0).toFixed(1) }) }))} label={t('analysis.overtakes.title')} />
    </ChartCard>
  )
}

function BattlesByRace({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.attacks !== null && c.attacks !== undefined)
  const parts = [
    ['attackWon', '#4ade80', (c: Cell) => c.attacks_won ?? 0],
    ['attackLost', '#166534', (c: Cell) => (c.attacks ?? 0) - (c.attacks_won ?? 0)],
    ['defenseWon', '#38bdf8', (c: Cell) => c.defenses_won ?? 0],
    ['defenseLost', '#1e3a8a', (c: Cell) => (c.defenses ?? 0) - (c.defenses_won ?? 0)],
  ] as const
  return (
    <ChartCard title={t('analysis.battles.title')} help={t('analysis.battles.help')} missing={rows.length === 0 ? t('analysis.noPositions') : null}>
      <StackChart
        label={t('analysis.battles.title')}
        legend={parts.map(([key, color]) => ({ label: t(`analysis.battles.${key}`), color }))}
        rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, parts: parts.map(([key, color, value]) => ({ key, label: t(`analysis.battles.${key}`), value: value(c), color })) }))}
      />
    </ChartCard>
  )
}

function IncidentsByRace({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.status && c.incidents !== null && c.incidents !== undefined)
  return (
    <ChartCard title={t('analysis.incidents.title')} help={t('analysis.incidents.help')} missing={rows.length === 0 ? t('analysis.noPositions') : null}>
      <BarChart rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: c.incidents as number, color: 'var(--danger)' }))} label={t('analysis.incidents.title')} />
    </ChartCard>
  )
}

function Forecast({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  return (
    <ChartCard title={t('analysis.forecast.title')} help={t('analysis.forecast.helpDriver')} missing={me.pace_forecast.length === 0 ? t('analysis.fewRounds', { count: 4 }) : null}>
      <LineChart series={forecastSeries(me)} xLabel={t('analysis.round')} yLabel={t('analysis.forecast.title')} invert formatY={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)} %`} />
    </ChartCard>
  )
}

/** The overall score is the mean of the parts of the radar, each with the same weight. */
function Decomposition({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const known = RADAR.filter((key) => me.scores[key] !== null && me.scores[key] !== undefined)
  const total = known.reduce((sum, key) => sum + (me.scores[key] as number), 0) / Math.max(known.length, 1)
  return (
    <ChartCard title={t('analysis.decomposition.title')} help={t('analysis.decomposition.help', { value: Math.round(total) })} missing={known.length === 0 ? t('analysis.radar.few') : null}>
      <BarChart rows={known.map((key) => ({ key, label: t(`analysis.radar.${key}`), value: me.scores[key] as number, color: driverColor(me.driver_id) }))} label={t('analysis.decomposition.title')} />
    </ChartCard>
  )
}

/** The distance between 2 drivers across all the parts of the radar. A part that one of them does
 * not have does not count. */
function Similarity({ season, me }: { season: Season; me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = season.drivers
    .filter((d) => d.driver_id !== me.driver_id)
    .flatMap((d) => {
      const shared = RADAR.filter((key) => me.scores[key] !== null && me.scores[key] !== undefined && d.scores[key] !== null && d.scores[key] !== undefined)
      if (shared.length < 2) return []
      const sum = shared.reduce((all, key) => all + ((me.scores[key] as number) - (d.scores[key] as number)) ** 2, 0)
      return [{ key: d.driver_id, label: d.name, value: Math.round(Math.sqrt(sum / shared.length)), color: driverColor(d.driver_id) }]
    })
    .sort((a, b) => a.value - b.value)
  return (
    <ChartCard title={t('analysis.similarity.title')} help={t('analysis.similarity.help')} missing={rows.length === 0 ? t('analysis.radar.few') : null}>
      <BarChart rows={rows} label={t('analysis.similarity.title')} />
    </ChartCard>
  )
}

/** The best lap of the driver on each track that the driver raced more than one time. A line goes
 * down when the driver gets faster. */
function TrackHistory({ seasons, driverId }: { seasons: Season[]; driverId: number }) {
  const { t } = useTranslation()
  const visits = new Map<string, number[]>()
  for (const season of [...seasons].reverse()) {
    for (const cell of season.drivers.find((d) => d.driver_id === driverId)?.cells ?? []) {
      if (cell.best_ms) visits.set(cell.track, [...(visits.get(cell.track) ?? []), cell.best_ms])
    }
  }
  const repeated = [...visits].filter(([, laps]) => laps.length > 1)
  const palette = (index: number) => `hsl(${(index * 67) % 360} 65% 60%)`
  const series: LineSeries[] = repeated.map(([track, laps], index) => {
    let best = Infinity
    return {
      key: track,
      label: track,
      color: palette(index),
      points: laps.map((ms, visit) => {
        const improved = ms < best
        best = Math.min(best, ms)
        return { x: visit + 1, y: (ms / laps[0] - 1) * 100, mark: improved }
      }),
    }
  })
  return (
    <ChartCard title={t('analysis.trackHistory.title')} help={t('analysis.trackHistory.help')} missing={series.length === 0 ? t('analysis.trackHistory.none') : null}>
      <LineChart series={series} xLabel={t('analysis.trackHistory.visit')} yLabel={t('analysis.trackHistory.title')} invert zero formatY={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)} %`} />
    </ChartCard>
  )
}

function GridFinish({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.grid && c.status)
  return (
    <ChartCard title={t('analysis.gridFinish.title')} help={t('analysis.gridFinish.help')} missing={rows.length === 0 ? t('analysis.noGrid') : null}>
      <LineChart
        xLabel={t('analysis.round')}
        yLabel={t('analysis.gridFinish.title')}
        invert
        integerY
        formatY={(v) => `P${v}`}
        series={[
          { key: 'grid', label: t('analysis.gridFinish.grid'), color: 'var(--ink-2)', dashed: true, points: rows.map((c) => ({ x: c.number, y: c.grid ?? null })) },
          { key: 'finish', label: t('analysis.gridFinish.finish'), color: driverColor(me.driver_id), points: rows.map((c) => ({ x: c.number, y: c.finish ?? null })) },
        ]}
      />
    </ChartCard>
  )
}

function QualifyingHistory({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.qualifying_pct !== null && c.qualifying_pct !== undefined)
  return (
    <ChartCard title={t('analysis.qualifyingHistory.title')} help={t('analysis.qualifyingHistory.help')} missing={rows.length === 0 ? t('analysis.noGrid') : null}>
      <BarChart rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: c.qualifying_pct as number, color: driverColor(me.driver_id), note: c.grid ? `P${c.grid}` : undefined }))} label={t('analysis.qualifyingHistory.title')} format={(v) => `+${v.toFixed(2)} %`} />
    </ChartCard>
  )
}

function PaceHistory({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.pace_pct !== null && c.pace_pct !== undefined)
  return (
    <ChartCard title={t('analysis.paceHistory.title')} help={t('analysis.paceHistory.help')} missing={rows.length === 0 ? t('analysis.noLaps') : null}>
      <BarChart rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: c.pace_pct as number, color: driverColor(me.driver_id) }))} label={t('analysis.paceHistory.title')} format={(v) => `+${v.toFixed(2)} %`} />
    </ChartCard>
  )
}

function FinishHistogram({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const finishes = raced(me).map((c) => c.finish).filter((f): f is number => !!f)
  const last = Math.max(1, ...finishes)
  const out = raced(me).filter((c) => c.status !== 'finished')
  return (
    <ChartCard title={t('analysis.histogram.title')} help={t('analysis.histogram.help')}>
      <BarChart
        label={t('analysis.histogram.title')}
        rows={[
          ...Array.from({ length: last }, (_, i) => ({ key: i, label: `P${i + 1}`, value: finishes.filter((f) => f === i + 1).length, color: driverColor(me.driver_id) })),
          { key: 'out', label: t('analysis.histogram.out'), value: out.length, color: 'var(--danger)' },
        ]}
      />
    </ChartCard>
  )
}

function GainedPerRace({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.grid && c.finish)
  return (
    <ChartCard title={t('analysis.gainedPerRace.title')} help={t('analysis.gained.help')} missing={rows.length === 0 ? t('analysis.noGrid') : null}>
      <BarChart rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: (c.grid as number) - (c.finish as number), color: driverColor(me.driver_id), note: `P${c.grid} → P${c.finish}` }))} label={t('analysis.gainedPerRace.title')} format={(v) => (v > 0 ? `+${v}` : String(v))} />
    </ChartCard>
  )
}

function BestVsTypical({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = me.cells.filter((c) => c.best_ms && c.median_ms)
  return (
    <ChartCard title={t('analysis.bestTypical.title')} help={t('analysis.bestTypical.help')} missing={rows.length === 0 ? t('analysis.noLaps') : null}>
      <BarChart
        rows={rows.map((c) => ({ key: c.number, label: `${c.number} · ${c.track}`, value: (c.median_ms as number) - (c.best_ms as number), color: driverColor(me.driver_id), note: `${formatLapTime(c.best_ms)} · ${formatLapTime(c.median_ms)}` }))}
        label={t('analysis.bestTypical.title')}
        format={(v) => `+${(v / 1000).toFixed(2)} s`}
      />
    </ChartCard>
  )
}

/** The rounds that both drivers raced. */
function shared(me: SeasonDriver, rival: SeasonDriver): [Cell, Cell][] {
  return me.cells.flatMap((cell) => {
    const other = rival.cells.find((c) => c.number === cell.number)
    return cell.status && other?.status ? ([[cell, other]] as [Cell, Cell][]) : []
  })
}

function HeadToHead({ me, rival }: { me: SeasonDriver; rival: SeasonDriver }) {
  const { t } = useTranslation()
  const rounds = shared(me, rival)
  const ahead = (mine: number | null | undefined, theirs: number | null | undefined) => !!mine && (!theirs || mine < theirs)
  const row = (label: string, mine: number, theirs: number) => ({
    key: label,
    label,
    note: `${mine} – ${theirs}`,
    parts: [
      { key: me.name, value: mine, color: driverColor(me.driver_id) },
      { key: rival.name, value: theirs, color: driverColor(rival.driver_id) },
    ],
  })
  return (
    <ChartCard title={t('analysis.headToHead.title', { a: me.name, b: rival.name })} help={t('analysis.headToHead.help')} missing={rounds.length === 0 ? t('analysis.noShared') : null}>
      <StackChart
        share
        label={t('analysis.headToHead.title', { a: me.name, b: rival.name })}
        legend={[me, rival].map((d) => ({ label: d.name, color: driverColor(d.driver_id) }))}
        rows={[
          row(t('analysis.headToHead.races'), rounds.filter(([a, b]) => ahead(a.finish, b.finish)).length, rounds.filter(([a, b]) => ahead(b.finish, a.finish)).length),
          row(t('analysis.headToHead.qualifying'), rounds.filter(([a, b]) => ahead(a.grid, b.grid)).length, rounds.filter(([a, b]) => ahead(b.grid, a.grid)).length),
          row(t('analysis.headToHead.pace'), rounds.filter(([a, b]) => a.median_ms && b.median_ms && a.median_ms < b.median_ms).length, rounds.filter(([a, b]) => a.median_ms && b.median_ms && b.median_ms < a.median_ms).length),
        ]}
      />
    </ChartCard>
  )
}

function PointsDuel({ me, rival }: { me: SeasonDriver; rival: SeasonDriver }) {
  const { t } = useTranslation()
  const line = (d: SeasonDriver): LineSeries => ({ key: d.driver_id, label: d.name, color: driverColor(d.driver_id), points: d.cells.filter((c) => c.rank).map((c) => ({ x: c.number, y: c.total_points })) })
  const series = [line(me), line(rival)]
  return (
    <ChartCard title={t('analysis.pointsDuel.title')} help={t('analysis.pointsDuel.help')} missing={shared(me, rival).length === 0 ? t('analysis.noShared') : null}>
      <LineChart series={series} xLabel={t('analysis.round')} yLabel={t('analysis.pointsDuel.title')} />
    </ChartCard>
  )
}

function PaceDuel({ me, rival }: { me: SeasonDriver; rival: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = shared(me, rival).filter(([a, b]) => a.median_ms && b.median_ms)
  return (
    <ChartCard title={t('analysis.paceDuel.title')} help={t('analysis.paceDuel.help', { a: me.name, b: rival.name })} missing={rows.length === 0 ? t('analysis.noShared') : null}>
      <BarChart
        rows={rows.map(([a, b]) => {
          const value = ((a.median_ms as number) - (b.median_ms as number)) / 1000
          return { key: a.number, label: `${a.number} · ${a.track}`, value, color: driverColor(value <= 0 ? me.driver_id : rival.driver_id) }
        })}
        label={t('analysis.paceDuel.title')}
        format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(3)} s`}
      />
    </ChartCard>
  )
}

function Reliability({ me }: { me: SeasonDriver }) {
  const { t } = useTranslation()
  const rows = raced(me)
  const groups = [
    ['finished', '#4ade80'],
    ['dnf', '#e5484d'],
    ['dns', '#94a3b8'],
    ['dsq', '#facc15'],
  ] as const
  return (
    <ChartCard title={t('analysis.reliability.title')} help={t('analysis.reliability.help')} missing={rows.length === 0 ? t('analysis.noDriverResults') : null}>
      <StackChart
        share
        label={t('analysis.reliability.title')}
        legend={groups.map(([k, color]) => ({ label: t(`analysis.status.${k}`), color }))}
        rows={[{ key: me.driver_id, label: me.name, note: String(rows.length), parts: groups.map(([k, color]) => ({ key: k, label: t(`analysis.status.${k}`), value: rows.filter((c) => c.status === k).length, color })) }]}
      />
    </ChartCard>
  )
}
