import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ActionForm } from '../components/ActionForm'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

const list = (value: FormDataEntryValue | null) =>
  String(value ?? '')
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)

const number = (value: FormDataEntryValue | null) => (value === null || value === '' ? null : Number(value))

/** The conditions pool of a season. The draw picks from these values. */
export function ConditionsPoolForm({ seasonId, onDone }: { seasonId: number; onDone?: () => void }) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const pool = useLoad(() => api.GET('/api/seasons/{season_id}/conditions-pool', { params: { path } }), [seasonId])
  if (!pool.data) return null
  const data = pool.data
  return (
    <div className="forms">
      <ActionForm
        title={t('draw.poolTitle')}
        submitLabel={t('common.save')}
        onDone={onDone}
        onSubmit={async (form) => {
          const { error } = await api.PUT('/api/seasons/{season_id}/conditions-pool', {
            params: { path },
            body: {
              weather: list(form.get('weather')),
              time_of_day: list(form.get('time_of_day')),
              grip: list(form.get('grip')),
              air_temp_min: number(form.get('air_temp_min')),
              air_temp_max: number(form.get('air_temp_max')),
              track_temp_min: number(form.get('track_temp_min')),
              track_temp_max: number(form.get('track_temp_max')),
            },
          })
          if (!error) pool.reload()
          return error
        }}
      >
        <p className="muted">{t('draw.poolHelp')}</p>
        <label>
          {t('briefing.weather')}
          <input name="weather" defaultValue={(data.weather ?? []).join(', ')} />
        </label>
        <label>
          {t('briefing.timeOfDay')}
          <input name="time_of_day" defaultValue={(data.time_of_day ?? []).join(', ')} />
        </label>
        <label>
          {t('briefing.grip')}
          <input name="grip" defaultValue={(data.grip ?? []).join(', ')} />
        </label>
        <div className="field-row">
          <label>
            {t('draw.airMin')}
            <input name="air_temp_min" type="number" defaultValue={data.air_temp_min ?? ''} />
          </label>
          <label>
            {t('draw.airMax')}
            <input name="air_temp_max" type="number" defaultValue={data.air_temp_max ?? ''} />
          </label>
          <label>
            {t('draw.trackMin')}
            <input name="track_temp_min" type="number" defaultValue={data.track_temp_min ?? ''} />
          </label>
          <label>
            {t('draw.trackMax')}
            <input name="track_temp_max" type="number" defaultValue={data.track_temp_max ?? ''} />
          </label>
        </div>
      </ActionForm>
    </div>
  )
}

/** The draws of a round, for everybody. */
export function DrawHistory({ roundId }: { roundId: number }) {
  const { t, i18n } = useTranslation()
  const draws = useLoad(
    () => api.GET('/api/rounds/{round_id}/conditions-draws', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  if (!draws.data || draws.data.length === 0) return null
  return (
    <details>
      <summary>{t('draw.history', { count: draws.data.length })}</summary>
      <ol>
        {draws.data.map((d, index) => (
          <li key={index}>
            {formatDateTime(d.drawn_at, i18n.language)} · {d.drawn_by ?? '—'}:{' '}
            {Object.values(d.values)
              .filter((v) => v !== null && v !== '')
              .join(' · ')}
            {d.reason && ` (${d.reason})`}
          </li>
        ))}
      </ol>
    </details>
  )
}
