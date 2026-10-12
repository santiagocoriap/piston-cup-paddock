import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import { ActionForm } from '../components/ActionForm'
import { Loading } from '../components/Layout'
import { formatDateTime, localInputToIso } from '../lib/format'
import { useLoad } from '../lib/useLoad'

export function SeasonPage() {
  const { t, i18n } = useTranslation()
  const seasonId = Number(useParams().seasonId)
  const path = { season_id: seasonId }
  const season = useLoad(() => api.GET('/api/seasons/{season_id}', { params: { path } }), [seasonId])

  const data = season.data
  if (!data) return <Loading failed={season.failed} />
  return (
    <section>
      <p className="muted">
        <Link to={`/championships/${data.championship_id}`}>{data.championship_name}</Link>
      </p>
      <h1>{data.name}</h1>
      <p className="muted">{t('season.plannedRounds', { count: data.planned_round_count })}</p>

      <h2>{t('season.calendar')}</h2>
      {data.rounds.length === 0 ? (
        <p>{t('season.noRounds')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('season.round')}</th>
                <th scope="col">{t('season.track')}</th>
                <th scope="col">{t('season.date')}</th>
                <th scope="col">{t('season.origin')}</th>
              </tr>
            </thead>
            <tbody>
              {data.rounds.map((round) => (
                <tr key={round.id}>
                  <td>{round.number}</td>
                  <td>
                    {round.track_name} · {round.layout_name}
                  </td>
                  <td>{formatDateTime(round.scheduled_at, i18n.language)}</td>
                  <td>
                    <span className="badge">{t(`season.origins.${round.origin}`)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>{t('season.entries')}</h2>
      {data.entries.length === 0 ? (
        <p>{t('season.noEntries')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('season.number')}</th>
                <th scope="col">{t('season.driver')}</th>
                <th scope="col">{t('season.car')}</th>
                <th scope="col">{t('season.team')}</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.number}</td>
                  <td>{entry.driver_name}</td>
                  <td>{entry.car_name}</td>
                  <td>{entry.team}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.can_manage && <SeasonForms seasonId={seasonId} onChange={season.reload} />}
    </section>
  )
}

function SeasonForms({ seasonId, onChange }: { seasonId: number; onChange: () => void }) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const drivers = useLoad(() => api.GET('/api/drivers'), [])

  return (
    <div className="forms">
      <ActionForm
        title={t('season.addRound')}
        submitLabel={t('common.add')}
        onSubmit={async (form) => {
          const { error } = await api.POST('/api/seasons/{season_id}/rounds', {
            params: { path },
            body: {
              track_layout_id: Number(form.get('track_layout_id')),
              scheduled_at: localInputToIso(String(form.get('scheduled_at'))),
            },
          })
          if (!error) onChange()
          return error
        }}
      >
        <label>
          {t('season.layout')}
          <select name="track_layout_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {tracks.data?.map((track) =>
              track.layouts.map((layout) => (
                <option key={layout.id} value={layout.id}>
                  {track.name} · {layout.name}
                </option>
              )),
            )}
          </select>
        </label>
        <label>
          {t('season.date')}
          <input name="scheduled_at" type="datetime-local" required />
        </label>
      </ActionForm>

      <ActionForm
        title={t('season.addEntry')}
        submitLabel={t('common.add')}
        onSubmit={async (form) => {
          const { error } = await api.POST('/api/seasons/{season_id}/entries', {
            params: { path },
            body: {
              driver_id: Number(form.get('driver_id')),
              car_id: Number(form.get('car_id')),
              number: Number(form.get('number')),
              team: String(form.get('team') ?? ''),
            },
          })
          if (!error) onChange()
          return error
        }}
      >
        <label>
          {t('season.driver')}
          <select name="driver_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {drivers.data?.map((driver) => (
              <option key={driver.id} value={driver.id}>
                {driver.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('season.car')}
          <select name="car_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {cars.data?.map((car) => (
              <option key={car.id} value={car.id}>
                {car.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('season.number')}
          <input name="number" type="number" min={1} max={999} required />
        </label>
        <label>
          {t('season.team')}
          <input name="team" maxLength={100} />
        </label>
      </ActionForm>
    </div>
  )
}
