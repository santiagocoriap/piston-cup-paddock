import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { formatLapTime } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { BarChart, ChartCard, ChartGroup, driverColor, LineChart, NeedsData, RadarChart, ScatterChart, StackChart, type LineSeries } from './charts'
import { type Season, type SeasonDriver } from './SeasonAnalysis'

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
      </ChartGroup>
      <ChartGroup title={t('analysis.groups.qualifyingRace')}>
        <GridFinish me={me} />
        <QualifyingHistory me={me} />
        <PaceHistory me={me} />
        <FinishHistogram me={me} />
        <GainedPerRace me={me} />
        <BestVsTypical me={me} />
      </ChartGroup>
      {rival && (
        <ChartGroup title={t('analysis.groups.headToHead')}>
          <HeadToHead me={me} rival={rival} />
          <PointsDuel me={me} rival={rival} />
          <PaceDuel me={me} rival={rival} />
        </ChartGroup>
      )}
      <ChartGroup title={t('analysis.groups.reliability')}>
        <Reliability me={me} />
      </ChartGroup>
      <NeedsData items={['overtakes', 'battles', 'circuitType', 'forecast'].map((key) => t(`analysis.needs.${key}`))} />
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
