import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { ActionForm } from '../../components/ActionForm'
import { Loading } from '../../components/Layout'
import { useLoad } from '../../lib/useLoad'

export function CatalogPage() {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])

  if (!tracks.data || !cars.data) return <Loading failed={tracks.failed || cars.failed} />
  return (
    <section>
      <h1>{t('catalog.title')}</h1>

      <h2>{t('catalog.tracks')}</h2>
      {tracks.data.length === 0 && <p>{t('catalog.noTracks')}</p>}
      <ul className="list">
        {tracks.data.map((track) => (
          <li key={track.id}>
            {track.name} <span className="mono muted">{track.key}</span>
            <ul>
              {track.layouts.map((layout) => (
                <li key={layout.id}>
                  {layout.name} <span className="mono muted">{layout.key}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>

      <h2>{t('catalog.cars')}</h2>
      {cars.data.length === 0 && <p>{t('catalog.noCars')}</p>}
      <ul className="list">
        {cars.data.map((car) => (
          <li key={car.id}>
            {car.name} <span className="mono muted">{car.key}</span>
          </li>
        ))}
      </ul>

      <div className="forms">
        <ActionForm
          title={t('catalog.newTrack')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/catalog/tracks', {
              body: { key: String(form.get('key')), name: String(form.get('name')) },
            })
            if (!error) tracks.reload()
            return error
          }}
        >
          <KeyAndName />
        </ActionForm>
        <ActionForm
          title={t('catalog.newLayout')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/catalog/tracks/{track_id}/layouts', {
              params: { path: { track_id: Number(form.get('track_id')) } },
              body: { key: String(form.get('key') ?? ''), name: String(form.get('name')) },
            })
            if (!error) tracks.reload()
            return error
          }}
        >
          <label>
            {t('catalog.track')}
            <select name="track_id" required defaultValue="">
              <option value="" disabled>
                {t('common.select')}
              </option>
              {tracks.data.map((track) => (
                <option key={track.id} value={track.id}>
                  {track.name}
                </option>
              ))}
            </select>
          </label>
          <KeyAndName keyRequired={false} keyHint={t('catalog.layoutKeyHint')} />
        </ActionForm>
        <ActionForm
          title={t('catalog.newCar')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/catalog/cars', {
              body: { key: String(form.get('key')), name: String(form.get('name')) },
            })
            if (!error) cars.reload()
            return error
          }}
        >
          <KeyAndName />
        </ActionForm>
      </div>
    </section>
  )
}

function KeyAndName({ keyRequired = true, keyHint }: { keyRequired?: boolean; keyHint?: string }) {
  const { t } = useTranslation()
  return (
    <>
      <label>
        {t('common.key')}
        <input name="key" required={keyRequired} maxLength={100} placeholder={keyHint} />
      </label>
      <label>
        {t('common.name')}
        <input name="name" required maxLength={200} />
      </label>
    </>
  )
}
