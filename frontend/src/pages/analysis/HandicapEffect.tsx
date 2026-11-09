import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useLoad } from '../../lib/useLoad'
import { BarChart, ChartCard, ChartGroup, driverColor } from './charts'

type Effect = components['schemas']['HandicapEffectOut']

const seconds = (ms: number | null | undefined, digits = 2) => (ms === null || ms === undefined ? '—' : `${(ms / 1000).toFixed(digits)} s`)
const percent = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)} %`)

/** How much time the ballast and the restrictor cost: the model estimate and the lap times. */
export function HandicapEffect({ seasonId, hidden }: { seasonId: number; hidden: number[] }) {
  const { t } = useTranslation()
  const load = useLoad(() => api.GET('/api/seasons/{season_id}/handicap-effect', { params: { path: { season_id: seasonId } } }), [seasonId])
  const data: Effect | undefined = load.data
  if (!data) return null
  const drivers = data.drivers.filter((d) => !hidden.includes(d.driver_id))
  const loaded = drivers.filter((d) => d.rounds.some((r) => r.ballast_kg || r.restrictor_pct))
  const help = t('analysis.handicap.help', { mass: data.mass_exponent, power: data.power_exponent, driver: data.driver_kg })
  return (
    <ChartGroup title={t('analysis.groups.handicap')}>
      <ChartCard
        title={t('analysis.handicap.total.title')}
        help={`${t('analysis.handicap.total.help')} ${help}`}
        missing={loaded.length === 0 ? t('analysis.handicap.none') : null}
        csv={() => [
          ['driver', 'round', 'ballast_kg', 'restrictor_pct', 'laps', 'model_ms_per_lap'],
          ...drivers.flatMap((d) => d.rounds.map((r) => [d.name, r.number, r.ballast_kg, r.restrictor_pct, r.laps ?? '', r.model_ms ?? ''])),
        ]}
      >
        <BarChart
          label={t('analysis.handicap.total.title')}
          format={(v) => `${v.toFixed(1)} s`}
          rows={[...loaded]
            .sort((a, b) => (b.model_total_ms ?? 0) - (a.model_total_ms ?? 0))
            .map((d) => ({
              key: d.entry_id,
              label: d.name,
              value: d.model_total_ms === null ? null : d.model_total_ms / 1000,
              color: driverColor(d.driver_id),
              note: t('analysis.handicap.perLap', { value: percent(d.model_pct) }),
            }))}
        />
      </ChartCard>
      <ChartCard
        wide
        title={t('analysis.handicap.table.title')}
        help={t('analysis.handicap.table.help')}
        missing={loaded.length === 0 ? t('analysis.handicap.none') : null}
      >
        <div className="table-wrap">
          <table className="handicap-table">
            <thead>
              <tr>
                <th scope="col">{t('analysis.handicap.table.driver')}</th>
                <th scope="col" className="r">{t('analysis.handicap.table.ballast')}</th>
                <th scope="col" className="r">{t('analysis.handicap.table.restrictor')}</th>
                <th scope="col" className="r">{t('analysis.handicap.table.model')}</th>
                <th scope="col" className="r">{t('analysis.handicap.table.total')}</th>
                <th scope="col" className="r">{t('analysis.handicap.table.measured')}</th>
              </tr>
            </thead>
            <tbody>
              {loaded.map((d) => {
                const rounds = d.rounds.filter((r) => r.ballast_kg || r.restrictor_pct)
                const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / (values.length || 1)
                const perLap = rounds.filter((r) => r.model_ms !== null).map((r) => r.model_ms as number)
                return (
                  <tr key={d.entry_id}>
                    <th scope="row">{d.name}</th>
                    <td className="r">{`${Math.round(mean(rounds.map((r) => r.ballast_kg)))} kg`}</td>
                    <td className="r">{`${mean(rounds.map((r) => r.restrictor_pct)).toFixed(1)} %`}</td>
                    <td className="r">{perLap.length ? `${seconds(mean(perLap), 3)} (${percent(d.model_pct)})` : '—'}</td>
                    <td className="r">{seconds(d.model_total_ms, 1)}</td>
                    <td className="r">{percent(d.measured_pct)}</td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">{t('analysis.handicap.table.all')}</th>
                <td />
                <td />
                <td className="r">{percent(data.model_pct)}</td>
                <td />
                <td className="r">{percent(data.measured_pct)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </ChartCard>
      <ChartCard wide title={t('analysis.handicap.cars.title')} help={t('analysis.handicap.cars.help')}>
        <div className="table-wrap">
          <table className="handicap-table">
            <thead>
              <tr>
                <th scope="col">{t('analysis.handicap.cars.car')}</th>
                <th scope="col" className="r">{t('analysis.handicap.cars.weight')}</th>
                <th scope="col" className="r">{t('analysis.handicap.cars.power')}</th>
                <th scope="col" className="r">{t('analysis.handicap.cars.lap')}</th>
                <th scope="col" className="r">{t('analysis.handicap.cars.per10kg')}</th>
                <th scope="col" className="r">{t('analysis.handicap.cars.per1pct')}</th>
              </tr>
            </thead>
            <tbody>
              {data.cars.map((car) => (
                <tr key={car.car_id}>
                  <th scope="row">{car.name}</th>
                  <td className="r">{car.weight_kg ? `${car.weight_kg} kg` : '—'}</td>
                  <td className="r">{car.power_hp ? `${car.power_hp} hp` : '—'}</td>
                  <td className="r">{seconds(car.lap_ms, 3)}</td>
                  <td className="r">{seconds(car.per_10kg_ms, 3)}</td>
                  <td className="r">{seconds(car.per_1pct_ms, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </ChartGroup>
  )
}
