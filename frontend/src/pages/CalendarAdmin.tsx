import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { localInputToIso } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type SeasonDetail = components['schemas']['SeasonDetail']

function optionalDate(value: FormDataEntryValue | null): string | null {
  return value ? localInputToIso(String(value)) : null
}

function optionalNumber(value: FormDataEntryValue | null): number | null {
  return value ? Number(value) : null
}

/** Admin forms for the calendar: reserve a fixed track, and set a round position or date. */
export function CalendarAdmin({ season, onChange }: { season: SeasonDetail; onChange: () => void }) {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])

  return (
    <div className="forms">
      <ActionForm
        title={t('calendar.fixed')}
        submitLabel={t('common.add')}
        onSubmit={async (form) => {
          const { error } = await api.POST('/api/seasons/{season_id}/fixed-rounds', {
            params: { path: { season_id: season.id } },
            body: {
              track_layout_id: Number(form.get('track_layout_id')),
              number: optionalNumber(form.get('number')),
              scheduled_at: optionalDate(form.get('scheduled_at')),
            },
          })
          if (!error) onChange()
          return error
        }}
      >
        <p className="muted">{t('calendar.fixedHelp')}</p>
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
        <div className="field-row">
          <label>
            {t('calendar.position')}
            <input name="number" type="number" min={1} max={99} />
          </label>
          <label>
            {t('calendar.date')}
            <input name="scheduled_at" type="datetime-local" />
          </label>
        </div>
      </ActionForm>

      {season.rounds.length > 0 && (
        <ActionForm
          title={t('calendar.edit')}
          submitLabel={t('common.save')}
          onSubmit={async (form) => {
            const { error } = await api.PATCH('/api/rounds/{round_id}/calendar', {
              params: { path: { round_id: Number(form.get('round_id')) } },
              body: {
                number: optionalNumber(form.get('number')),
                scheduled_at: optionalDate(form.get('scheduled_at')),
              },
            })
            if (!error) onChange()
            return error
          }}
        >
          <label>
            {t('calendar.round')}
            <select name="round_id" required defaultValue="">
              <option value="" disabled>
                {t('common.select')}
              </option>
              {season.rounds.map((round) => (
                <option key={round.id} value={round.id}>
                  R{round.number} · {round.track_name} · {round.layout_name}
                </option>
              ))}
            </select>
          </label>
          <div className="field-row">
            <label>
              {t('calendar.position')}
              <input name="number" type="number" min={1} max={99} />
            </label>
            <label>
              {t('calendar.date')}
              <input name="scheduled_at" type="datetime-local" />
            </label>
          </div>
        </ActionForm>
      )}
    </div>
  )
}
