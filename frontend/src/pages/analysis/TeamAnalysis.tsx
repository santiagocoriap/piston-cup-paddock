import { useTranslation } from 'react-i18next'
import { BarChart, ChartCard, ChartGroup, driverColor, LineChart, StackChart, type LineSeries } from './charts'
import type { Season, SeasonDriver } from './SeasonAnalysis'

type Team = { name: string; color: string; drivers: SeasonDriver[] }

const TEAM_COLORS = ['#e5484d', '#38bdf8', '#f5c542', '#22c55e', '#a78bfa', '#fb923c', '#f472b6', '#94a3b8']
const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null)

/** The teams of the season, from the team of each entry. The team with more points first. */
export function seasonTeams(drivers: SeasonDriver[]): Team[] {
  const groups = new Map<string, SeasonDriver[]>()
  for (const driver of drivers) {
    if (!driver.team) continue
    groups.set(driver.team, [...(groups.get(driver.team) ?? []), driver])
  }
  const points = (members: SeasonDriver[]) => members.reduce((sum, d) => sum + d.points, 0)
  return [...groups.entries()]
    .sort((a, b) => points(b[1]) - points(a[1]) || a[0].localeCompare(b[0]))
    .map(([name, members], index) => ({ name, color: TEAM_COLORS[index % TEAM_COLORS.length], drivers: members }))
}

/** Teammates against each other: who finished ahead, who started ahead, and the points. */
export function headToHead(a: SeasonDriver, b: SeasonDriver) {
  let races = 0
  let raceA = 0
  let grids = 0
  let gridA = 0
  for (const cell of a.cells) {
    const other = b.cells.find((c) => c.number === cell.number)
    if (!other) continue
    if (cell.finish && other.finish) {
      races += 1
      if (cell.finish < other.finish) raceA += 1
    }
    if (cell.grid && other.grid) {
      grids += 1
      if (cell.grid < other.grid) gridA += 1
    }
  }
  return { races, raceA, raceB: races - raceA, grids, gridA, gridB: grids - gridA }
}

/** The team section of the season analysis. */
export function TeamAnalysis({ season, drivers }: { season: Season; drivers: SeasonDriver[] }) {
  const { t } = useTranslation()
  const teams = seasonTeams(drivers)
  const done = new Set(season.rounds.filter((r) => r.has_result).map((r) => r.number))
  const none = teams.length === 0 ? t('analysis.teams.none') : null
  const total = (team: Team) => team.drivers.reduce((sum, d) => sum + d.points, 0)

  const pointsSeries: LineSeries[] = teams.map((team) => ({
    key: team.name,
    label: team.name,
    color: team.color,
    points: [...done]
      .sort((a, b) => a - b)
      .map((number) => ({
        x: number,
        y: team.drivers.reduce((sum, d) => sum + (d.cells.find((c) => c.number === number)?.total_points ?? 0), 0),
      })),
  }))

  const paceSeries: LineSeries[] = teams.map((team) => ({
    key: team.name,
    label: team.name,
    color: team.color,
    points: [...done]
      .sort((a, b) => a - b)
      .map((number) => ({
        x: number,
        y: mean(
          team.drivers
            .map((d) => d.cells.find((c) => c.number === number)?.pace_pct)
            .filter((v): v is number => v !== null && v !== undefined),
        ),
      })),
  }))

  const pairs = teams.flatMap((team) => {
    const members = [...team.drivers].sort((a, b) => b.points - a.points)
    return members.slice(1).map((other) => ({ team, a: members[0], b: other, score: headToHead(members[0], other) }))
  })

  return (
    <ChartGroup title={t('analysis.groups.teams')}>
      <ChartCard
        title={t('analysis.teams.standings.title')}
        help={t('analysis.teams.standings.help')}
        missing={none}
        csv={() => [['team', 'driver', 'points'], ...teams.flatMap((team) => team.drivers.map((d) => [team.name, d.name, d.points]))]}
      >
        <StackChart
          label={t('analysis.teams.standings.title')}
          rows={teams.map((team) => ({
            key: team.name,
            label: team.name,
            note: String(total(team)),
            parts: team.drivers.map((d) => ({ key: String(d.driver_id), label: d.name, value: d.points, color: driverColor(d.driver_id) })),
          }))}
        />
      </ChartCard>
      <ChartCard title={t('analysis.teams.points.title')} help={t('analysis.teams.points.help')} missing={none ?? (done.size < 2 ? t('analysis.fewRounds', { count: 2 }) : null)}>
        <LineChart series={pointsSeries} xLabel={t('analysis.round')} yLabel={t('analysis.teams.points.title')} />
      </ChartCard>
      <ChartCard title={t('analysis.teams.pace.title')} help={t('analysis.teams.pace.help')} missing={none}>
        <LineChart series={paceSeries} xLabel={t('analysis.round')} yLabel={t('analysis.teams.pace.title')} invert formatY={(v) => `+${v.toFixed(1)} %`} />
      </ChartCard>
      <ChartCard title={t('analysis.teams.share.title')} help={t('analysis.teams.share.help')} missing={none}>
        <BarChart
          label={t('analysis.teams.share.title')}
          format={(v) => `${Math.round(v)} %`}
          rows={teams.flatMap((team) =>
            team.drivers.map((d) => ({
              key: d.driver_id,
              label: `${d.name} · ${team.name}`,
              value: total(team) ? (d.points / total(team)) * 100 : null,
              color: team.color,
            })),
          )}
        />
      </ChartCard>
      <ChartCard wide title={t('analysis.teams.duels.title')} help={t('analysis.teams.duels.help')} missing={pairs.length === 0 ? t('analysis.teams.noPairs') : null}>
        <div className="table-wrap">
          <table className="team-duels">
            <thead>
              <tr>
                <th scope="col">{t('analysis.teams.duels.team')}</th>
                <th scope="col">{t('analysis.teams.duels.drivers')}</th>
                <th scope="col" className="r">{t('analysis.teams.duels.race')}</th>
                <th scope="col" className="r">{t('analysis.teams.duels.grid')}</th>
                <th scope="col" className="r">{t('analysis.teams.duels.points')}</th>
              </tr>
            </thead>
            <tbody>
              {pairs.map(({ team, a, b, score }) => (
                <tr key={`${a.driver_id}-${b.driver_id}`}>
                  <th scope="row">
                    <i className="team-swatch" style={{ background: team.color }} aria-hidden="true" />
                    {team.name}
                  </th>
                  <td>
                    {a.name} – {b.name}
                  </td>
                  <td className="r">{score.races ? `${score.raceA} – ${score.raceB}` : '—'}</td>
                  <td className="r">{score.grids ? `${score.gridA} – ${score.gridB}` : '—'}</td>
                  <td className="r">
                    {a.points} – {b.points}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </ChartGroup>
  )
}
