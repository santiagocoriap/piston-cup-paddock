import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useLoad } from '../../lib/useLoad'
import { BarChart, BoxChart, ChartCard, ChartGroup, DriverFilter, driverColor, HeatMap, LineChart, NeedsData, ScatterChart, StackChart, type BoxRow, type LineSeries } from './charts'

export type Season = components['schemas']['SeasonAnalysisOut']
export type SeasonDriver = components['schemas']['SeasonDriverOut']
type Cell = components['schemas']['RoundCellOut']

const MIN_ROUNDS = 2
export const PREDICT_ROUNDS = 3
const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null)
const FINISH_COLORS = ['#f5c542', '#cbd5e1', '#d9915b', '#38bdf8', '#64748b', '#e5484d']

/** The rounds of a season with a result. A driver has a cell for each round of the calendar. */
function raced(season: Season) {
  return season.rounds.filter((r) => r.has_result)
}

/** A line for each driver, with one point for each round with a result. */
function roundSeries(season: Season, drivers: SeasonDriver[], value: (cell: Cell) => number | null | undefined): LineSeries[] {
  const done = new Set(raced(season).map((r) => r.number))
  return drivers.map((d) => ({
    key: d.driver_id,
    label: d.name,
    color: driverColor(d.driver_id),
    points: d.cells.filter((c) => done.has(c.number)).map((c) => ({ x: c.number, y: value(c) ?? null })),
  }))
}

function quantile(sorted: number[], share: number) {
  const place = (sorted.length - 1) * share
  const low = Math.floor(place)
  return sorted[low] + (sorted[Math.min(low + 1, sorted.length - 1)] - sorted[low]) * (place - low)
}

/** The data analysis section of a season page. */
export function SeasonAnalysis({ seasonId }: { seasonId: number }) {
  const { t } = useTranslation()
  const load = useLoad(() => api.GET('/api/seasons/{season_id}/analysis', { params: { path: { season_id: seasonId } } }), [seasonId])
  const [hidden, setHidden] = useState<number[]>([])
  const season = load.data
  if (!season) return null
  if (raced(season).length === 0) {
    return (
      <>
        <h2>{t('analysis.title')}</h2>
        <p className="muted">{t('analysis.noResults')}</p>
      </>
    )
  }
  const drivers = season.drivers.filter((d) => !hidden.includes(d.driver_id))
  const few = raced(season).length < MIN_ROUNDS ? t('analysis.fewRounds', { count: MIN_ROUNDS }) : null
  return (
    <div className="analysis">
      <h2>{t('analysis.title')}</h2>
      <div className="analysis-bar">
        <DriverFilter drivers={season.drivers.map((d) => ({ id: d.driver_id, name: d.name }))} hidden={hidden} onChange={setHidden} />
      </div>
      <ChartGroup title={t('analysis.groups.championship')} open>
        <ChartCard title={t('analysis.points.title')} help={t('analysis.points.help')} missing={few} csv={() => [['driver', 'round', 'points'], ...drivers.flatMap((d) => d.cells.map((c) => [d.name, c.number, c.total_points]))]}>
          <LineChart series={roundSeries(season, drivers, (c) => c.total_points)} xLabel={t('analysis.round')} yLabel={t('analysis.points.title')} />
        </ChartCard>
        <ChartCard title={t('analysis.rank.title')} help={t('analysis.rank.help')} missing={few}>
          <LineChart series={roundSeries(season, drivers, (c) => c.rank)} xLabel={t('analysis.round')} yLabel={t('analysis.rank.title')} invert integerY formatY={(v) => `P${v}`} />
        </ChartCard>
        <ChartCard title={t('analysis.gapPoints.title')} help={t('analysis.gapPoints.help')} missing={few}>
          <LineChart series={roundSeries(season, drivers, (c) => c.gap_to_leader)} xLabel={t('analysis.round')} yLabel={t('analysis.gapPoints.title')} invert formatY={(v) => `-${Math.round(v)}`} />
        </ChartCard>
        <ContributionChart season={season} drivers={drivers} />
        <MomentumChart season={season} drivers={drivers} few={raced(season).length < PREDICT_ROUNDS ? t('analysis.fewRounds', { count: PREDICT_ROUNDS }) : null} />
        <ContentionChart season={season} drivers={drivers} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.competitiveness')}>
        <CalendarHeat season={season} drivers={drivers} />
        <FinishBox season={season} drivers={drivers} few={few} />
        <PaceHeat season={season} drivers={drivers} />
        <QualifyingHeat season={season} drivers={drivers} />
        <QualifyingScatter drivers={drivers} />
        <SeasonGained drivers={drivers} />
        <SeasonConsistency drivers={drivers} />
        <FieldSpread season={season} few={few} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.records')}>
        <HonoursChart drivers={drivers} />
        <FinishFrequency drivers={drivers} />
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.predictions')}>
        <PredictionChart season={season} drivers={drivers} />
      </ChartGroup>
      <NeedsData items={['rivalry', 'scenario', 'circuitType'].map((key) => t(`analysis.needs.${key}`))} />
    </div>
  )
}

function ContributionChart({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const shades = (i: number) => `hsl(${(i * 47) % 360} 65% 55%)`
  return (
    <ChartCard title={t('analysis.contribution.title')} help={t('analysis.contribution.help')}>
      <StackChart
        label={t('analysis.contribution.title')}
        legend={raced(season).map((r, i) => ({ label: `${r.number} · ${r.track}`, color: shades(i) }))}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          parts: raced(season).map((r, i) => ({ key: String(r.number), label: r.track, value: Math.max(d.cells.find((c) => c.number === r.number)?.points ?? 0, 0), color: shades(i) })),
        }))}
      />
    </ChartCard>
  )
}

function MomentumChart({ season, drivers, few }: { season: Season; drivers: SeasonDriver[]; few: string | null }) {
  const { t } = useTranslation()
  const size = 3
  const done = raced(season).map((r) => r.number)
  const series = drivers.map((d) => ({
    key: d.driver_id,
    label: d.name,
    color: driverColor(d.driver_id),
    points: done.map((number, index) => {
      const part = done.slice(Math.max(0, index - size + 1), index + 1).map((n) => d.cells.find((c) => c.number === n)?.points ?? 0)
      return { x: number, y: part.length === size ? (mean(part) as number) : null }
    }),
  }))
  return (
    <ChartCard title={t('analysis.momentum.title')} help={t('analysis.momentum.help', { count: size })} missing={few}>
      <LineChart series={series} xLabel={t('analysis.round')} yLabel={t('analysis.momentum.title')} />
    </ChartCard>
  )
}

function ContentionChart({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const leader = season.drivers[0]?.points ?? 0
  return (
    <ChartCard title={t('analysis.contention.title')} help={t('analysis.contention.help', { rounds: season.remaining_rounds, points: season.points_by_position[0] ?? 0 })}>
      <BarChart
        label={t('analysis.contention.title')}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          value: leader - d.points,
          muted: d.can_win === false,
          color: driverColor(d.driver_id),
          note: d.can_win === false ? t('analysis.contention.out') : t('analysis.contention.max', { points: d.max_points }),
        }))}
        format={(v) => `-${v}`}
      />
    </ChartCard>
  )
}

function CalendarHeat({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const done = raced(season)
  return (
    <ChartCard wide title={t('analysis.calendar.title')} help={t('analysis.calendar.help')}>
      <HeatMap
        label={t('analysis.calendar.title')}
        columns={done.map((r) => String(r.number))}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          cells: done.map((r) => {
            const c = d.cells.find((cell) => cell.number === r.number)
            if (!c || !c.status) return { value: null }
            return { value: c.finish ?? 99, text: c.finish ? String(c.finish) : c.status.toUpperCase().slice(0, 3), title: `${r.track} · ${c.points} pts` }
          }),
        }))}
        low={1}
        high={Math.max(2, season.drivers.length)}
      />
    </ChartCard>
  )
}

function FinishBox({ season, drivers, few }: { season: Season; drivers: SeasonDriver[]; few: string | null }) {
  const { t } = useTranslation()
  void season
  const rows: BoxRow[] = drivers.flatMap((d) => {
    const finishes = d.cells.map((c) => c.finish).filter((f): f is number => !!f).sort((a, b) => a - b)
    if (finishes.length < MIN_ROUNDS) return []
    return [{ key: d.driver_id, label: d.name, color: driverColor(d.driver_id), q1: quantile(finishes, 0.25), q3: quantile(finishes, 0.75), median: quantile(finishes, 0.5), low: finishes[0], high: finishes[finishes.length - 1], outliers: [], note: `n=${finishes.length}` }]
  })
  return (
    <ChartCard title={t('analysis.finishBox.title')} help={t('analysis.finishBox.help')} missing={few ?? (rows.length === 0 ? t('analysis.fewRounds', { count: MIN_ROUNDS }) : null)}>
      {rows.length > 0 && <BoxChart rows={rows} format={(v) => `P${v % 1 === 0 ? v : v.toFixed(1)}`} label={t('analysis.finishBox.title')} />}
    </ChartCard>
  )
}

function PaceHeat({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const done = raced(season)
  const any = drivers.some((d) => d.cells.some((c) => c.pace_pct !== null))
  return (
    <ChartCard title={t('analysis.paceHeat.title')} help={t('analysis.paceHeat.help')} missing={any ? null : t('analysis.noLaps')}>
      <HeatMap
        label={t('analysis.paceHeat.title')}
        columns={done.map((r) => String(r.number))}
        low={0}
        high={3}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          cells: done.map((r) => {
            const c = d.cells.find((cell) => cell.number === r.number)
            return c?.pace_pct === null || c?.pace_pct === undefined ? { value: null } : { value: c.pace_pct, text: `+${c.pace_pct.toFixed(1)}`, title: `${r.track} · +${c.pace_pct.toFixed(2)} %` }
          }),
        }))}
      />
    </ChartCard>
  )
}

function QualifyingHeat({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const done = raced(season)
  const any = drivers.some((d) => d.cells.some((c) => c.grid))
  return (
    <ChartCard title={t('analysis.qualifyingHeat.title')} help={t('analysis.qualifyingHeat.help')} missing={any ? null : t('analysis.noGrid')}>
      <HeatMap
        label={t('analysis.qualifyingHeat.title')}
        columns={done.map((r) => String(r.number))}
        low={0}
        high={3}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          cells: done.map((r) => {
            const c = d.cells.find((cell) => cell.number === r.number)
            return c?.qualifying_pct === null || c?.qualifying_pct === undefined ? { value: null } : { value: c.qualifying_pct, text: c.grid ? `P${c.grid}` : undefined, title: `${r.track} · +${c.qualifying_pct.toFixed(2)} %` }
          }),
        }))}
      />
    </ChartCard>
  )
}

function QualifyingScatter({ drivers }: { drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const points = drivers.flatMap((d) => {
    const grid = mean(d.cells.map((c) => c.grid).filter((g): g is number => !!g))
    const finish = mean(d.cells.map((c) => c.finish).filter((f): f is number => !!f))
    return grid !== null && finish !== null ? [{ key: d.driver_id, label: d.name, x: grid, y: finish, color: driverColor(d.driver_id) }] : []
  })
  return (
    <ChartCard title={t('analysis.qualifyingScatter.title')} help={t('analysis.qualifyingScatter.help')} missing={points.length < 2 ? t('analysis.noGrid') : null}>
      <ScatterChart points={points} xLabel={t('analysis.qualifyingScatter.x')} yLabel={t('analysis.qualifyingScatter.y')} invertY diagonal formatX={(v) => `P${v.toFixed(1)}`} formatY={(v) => `P${v.toFixed(1)}`} />
    </ChartCard>
  )
}

function SeasonGained({ drivers }: { drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const rows = drivers
    .map((d) => ({ key: d.driver_id, label: d.name, value: d.cells.reduce((sum, c) => sum + (c.grid && c.finish ? c.grid - c.finish : 0), 0), color: driverColor(d.driver_id) }))
    .sort((a, b) => b.value - a.value)
  return (
    <ChartCard title={t('analysis.seasonGained.title')} help={t('analysis.seasonGained.help')} missing={drivers.some((d) => d.cells.some((c) => c.grid)) ? null : t('analysis.noGrid')}>
      <BarChart rows={rows} label={t('analysis.seasonGained.title')} format={(v) => (v > 0 ? `+${v}` : String(v))} />
    </ChartCard>
  )
}

function SeasonConsistency({ drivers }: { drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const rows = drivers
    .filter((d) => d.average_stdev_ms !== null && d.average_stdev_ms !== undefined)
    .sort((a, b) => (a.average_stdev_ms as number) - (b.average_stdev_ms as number))
    .map((d) => ({ key: d.driver_id, label: d.name, value: d.average_stdev_ms as number, color: driverColor(d.driver_id) }))
  return (
    <ChartCard title={t('analysis.seasonConsistency.title')} help={t('analysis.seasonConsistency.help')} missing={rows.length === 0 ? t('analysis.noLaps') : null}>
      <BarChart rows={rows} label={t('analysis.seasonConsistency.title')} format={(v) => `${(v / 1000).toFixed(3)} s`} />
    </ChartCard>
  )
}

function FieldSpread({ season, few }: { season: Season; few: string | null }) {
  const { t } = useTranslation()
  return (
    <ChartCard title={t('analysis.fieldSpread.title')} help={t('analysis.fieldSpread.help')} missing={few}>
      <LineChart
        series={[{ key: 'spread', label: t('analysis.fieldSpread.title'), color: 'var(--brand)', points: raced(season).map((r) => ({ x: r.number, y: r.field_spread_pct ?? null })) }]}
        xLabel={t('analysis.round')}
        yLabel={t('analysis.fieldSpread.title')}
        formatY={(v) => `${v.toFixed(2)} %`}
      />
    </ChartCard>
  )
}

function HonoursChart({ drivers }: { drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const kinds = [
    ['wins', '#f5c542'],
    ['podiums', '#cbd5e1'],
    ['poles', '#38bdf8'],
    ['fastest_laps', '#c084fc'],
  ] as const
  return (
    <ChartCard title={t('analysis.honours.title')} help={t('analysis.honours.help')} csv={() => [['driver', ...kinds.map(([k]) => k)], ...drivers.map((d) => [d.name, ...kinds.map(([k]) => d[k])])]}>
      <StackChart
        label={t('analysis.honours.title')}
        legend={kinds.map(([k, color]) => ({ label: t(`analysis.honours.${k}`), color }))}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          note: kinds.map(([k]) => d[k]).join(' / '),
          parts: kinds.map(([k, color]) => ({ key: k, label: t(`analysis.honours.${k}`), value: d[k], color })),
        }))}
      />
    </ChartCard>
  )
}

function FinishFrequency({ drivers }: { drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const groups: [string, (c: Cell) => boolean][] = [
    ['P1', (c) => c.finish === 1],
    ['P2', (c) => c.finish === 2],
    ['P3', (c) => c.finish === 3],
    ['P4–P5', (c) => !!c.finish && c.finish > 3 && c.finish <= 5],
    ['P6+', (c) => !!c.finish && c.finish > 5],
    ['DNF', (c) => !!c.status && c.status !== 'finished'],
  ]
  return (
    <ChartCard title={t('analysis.frequency.title')} help={t('analysis.frequency.help')}>
      <StackChart
        label={t('analysis.frequency.title')}
        legend={groups.map(([name], i) => ({ label: name, color: FINISH_COLORS[i] }))}
        rows={drivers.map((d) => ({
          key: d.driver_id,
          label: d.name,
          parts: groups.map(([name, test], i) => ({ key: name, value: d.cells.filter(test).length, color: FINISH_COLORS[i] })),
        }))}
      />
    </ChartCard>
  )
}

function PredictionChart({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const known = drivers.filter((d) => d.win_pct !== null && d.win_pct !== undefined)
  const missing =
    raced(season).length < PREDICT_ROUNDS
      ? t('analysis.fewRounds', { count: PREDICT_ROUNDS })
      : season.remaining_rounds === 0
        ? t('analysis.prediction.over')
        : null
  const shades = (i: number) => `hsl(${130 - (i * 130) / Math.max(season.drivers.length - 1, 1)} 60% 45%)`
  return (
    <>
      <ChartCard title={t('analysis.prediction.title')} help={t('analysis.prediction.help', { runs: 2000 })} missing={missing}>
        <BarChart
          label={t('analysis.prediction.title')}
          rows={[...known].sort((a, b) => (b.win_pct as number) - (a.win_pct as number)).map((d) => ({ key: d.driver_id, label: d.name, value: d.win_pct as number, color: driverColor(d.driver_id) }))}
          format={(v) => `${v.toFixed(1)} %`}
        />
      </ChartCard>
      <ChartCard title={t('analysis.predictedRank.title')} help={t('analysis.predictedRank.help')} missing={missing}>
        <StackChart
          share
          label={t('analysis.predictedRank.title')}
          legend={season.drivers.map((_, i) => ({ label: `P${i + 1}`, color: shades(i) }))}
          rows={[...known].sort((a, b) => (a.expected_rank as number) - (b.expected_rank as number)).map((d) => ({
            key: d.driver_id,
            label: d.name,
            note: `≈ P${(d.expected_rank as number).toFixed(1)}`,
            parts: (d.rank_odds ?? []).map((odds, i) => ({ key: `P${i + 1}`, value: odds, color: shades(i) })),
          }))}
          format={(v) => `${v.toFixed(1)} %`}
        />
      </ChartCard>
    </>
  )
}
