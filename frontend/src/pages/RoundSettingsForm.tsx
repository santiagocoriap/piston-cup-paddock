import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { isoToLocalInput, localInputToIso } from '../lib/format'

type RoundOut = components['schemas']['RoundOut']

// The weather folders of Assetto Corsa with Sol. The server takes only these IDs.
const WEATHERS = [
  'sol_01_clear',
  'sol_02_few_clouds',
  'sol_03_scattered_clouds',
  'sol_04_windy',
  'sol_05_broken_clouds',
  'sol_06_overcast',
  'sol_11_mist',
  'sol_12_fog',
  'sol_21_haze',
  'sol_31_light_drizzle',
  'sol_32_drizzle',
  'sol_34_light_rain',
  'sol_35_rain',
  'sol_36_heavy_rain',
  'sol_41_light_thunderstorm',
  'sol_42_thunderstorm',
]
const GRIPS = ['Dusty (86%)', 'Old (90%)', 'Slow (96%)', 'Green (95%)', 'Fast (98%)', 'Optimum (100%)']

function optionalNumber(value: FormDataEntryValue | null): number | null {
  return value === null || value === '' ? null : Number(value)
}

/** The date and the conditions of one round, for an admin. The fields show the current values. */
export function RoundSettingsForm({
  round,
  onChange,
  onDone,
}: {
  round: RoundOut
  onChange: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const now = (round.announced_conditions ?? {}) as Record<string, string | number | null>
  const text = (key: string) => (now[key] === null || now[key] === undefined ? '' : String(now[key]))
  return (
    <ActionForm
      title={t('roundTools.settingsTitle', { number: round.number, track: round.track_name })}
      submitLabel={t('common.save')}
      onDone={onDone}
      onSubmit={async (form) => {
        const field = (name: string) => String(form.get(name) ?? '').trim()
        const date = field('scheduled_at')
        const { error } = await api.PATCH('/api/rounds/{round_id}/calendar', {
          params: { path: { round_id: round.id } },
          body: {
            scheduled_at: date ? localInputToIso(date) : null,
            announced_conditions: {
              time_of_day: field('time_of_day'),
              weather: field('weather'),
              air_temp_c: optionalNumber(form.get('air_temp_c')),
              track_temp_c: optionalNumber(form.get('track_temp_c')),
              grip: field('grip'),
              notes: field('notes'),
            },
          },
        })
        if (!error) onChange()
        return error
      }}
    >
      <label>
        {t('calendar.date')}
        <input
          name="scheduled_at"
          type="datetime-local"
          defaultValue={round.scheduled_at ? isoToLocalInput(round.scheduled_at) : ''}
        />
      </label>
      <fieldset className="conditions-fields">
        <legend>{t('briefing.conditions')}</legend>
        <p className="muted">{t('roundTools.conditionsHelp')}</p>
        <div className="field-row">
          <label>
            {t('briefing.timeOfDay')}
            <input name="time_of_day" type="time" defaultValue={text('time_of_day')} />
          </label>
          <label>
            {t('briefing.weather')}
            <select name="weather" defaultValue={text('weather')}>
              <option value="">{t('roundTools.weatherKeep')}</option>
              {text('weather') && !WEATHERS.includes(text('weather')) && (
                <option value={text('weather')}>{text('weather')}</option>
              )}
              {WEATHERS.map((name) => (
                <option key={name} value={name}>
                  {t(`roundTools.weathers.${name}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field-row">
          <label>
            {t('briefing.airTemp')} (°C)
            <input name="air_temp_c" type="number" min={-30} max={60} defaultValue={text('air_temp_c')} />
          </label>
          <label>
            {t('briefing.trackTemp')} (°C)
            <input name="track_temp_c" type="number" min={-30} max={80} defaultValue={text('track_temp_c')} />
          </label>
          <label>
            {t('briefing.grip')}
            <input name="grip" list="grip-names" maxLength={50} defaultValue={text('grip')} />
            <datalist id="grip-names">
              {GRIPS.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
        </div>
        <label>
          {t('briefing.notes')}
          <input name="notes" maxLength={500} defaultValue={text('notes')} />
        </label>
      </fieldset>
    </ActionForm>
  )
}
