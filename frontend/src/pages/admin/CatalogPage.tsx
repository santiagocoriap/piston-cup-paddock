import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { Loading } from '../../components/Layout'
import { useLoad } from '../../lib/useLoad'
import { CarClassesSection } from './CarClassesSection'
import { GameImagesSection } from './GameImagesSection'

export function CatalogPage() {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])

  if (!tracks.data || !cars.data) return <Loading failed={tracks.failed || cars.failed} />
  return (
    <section>
      <h1>{t('catalog.title')}</h1>
      <GameImagesSection
        onImported={() => {
          tracks.reload()
          cars.reload()
        }}
      />

      <h2>{t('catalog.tracks')}</h2>
      {tracks.data.length === 0 && <p>{t('catalog.noTracks')}</p>}
      <ul className="list">
        {tracks.data.map((track) => (
          <li key={track.id}>
            {track.name} <span className="mono muted">{track.key}</span>
            <ul>
              {track.layouts.map((layout) => (
                <li key={layout.id}>
                  {layout.has_outline && (
                    <img className="thumb" src={`/api/catalog/layouts/${layout.id}/images/outline`} alt="" />
                  )}
                  {layout.name} <span className="mono muted">{layout.key}</span>
                  {layout.length_m && <span className="muted"> · {(layout.length_m / 1000).toFixed(3)} km</span>}
                  <GuidanceForm layout={layout} onSaved={tracks.reload} />
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
            {car.has_preview && (
              <img className="thumb car" src={`/api/catalog/cars/${car.id}/images/preview`} alt="" />
            )}
            {car.name} <span className="mono muted">{car.key}</span>
            {car.author && <span className="muted"> · {t('catalog.images.author', { author: car.author })}</span>}
          </li>
        ))}
      </ul>

      {cars.data && <CarClassesSection cars={cars.data} />}

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

type Layout = components['schemas']['LayoutOut']

/** The first-lap restart guidance of one layout. The round briefing shows it. */
function GuidanceForm({ layout, onSaved }: { layout: Layout; onSaved: () => void }) {
  const { t } = useTranslation()
  return (
    <details>
      <summary>{t('catalog.guidance')}</summary>
      <ActionForm
        title={t('catalog.guidanceFor', { name: layout.name })}
        submitLabel={t('common.save')}
        onSubmit={async (form) => {
          const { error } = await api.PATCH('/api/catalog/layouts/{layout_id}/guidance', {
            params: { path: { layout_id: layout.id } },
            body: {
              restart_guidance: String(form.get('restart_guidance') ?? ''),
              first_lap_cutoff: String(form.get('first_lap_cutoff') ?? ''),
              pit_boxes: form.get('pit_boxes') ? Number(form.get('pit_boxes')) : null,
            },
          })
          if (!error) onSaved()
          return error
        }}
      >
        <label>
          {t('catalog.cutoff')}
          <input name="first_lap_cutoff" defaultValue={layout.first_lap_cutoff} maxLength={200} />
        </label>
        <label>
          {t('catalog.pitBoxes')}
          <input name="pit_boxes" type="number" min={1} max={200} defaultValue={layout.pit_boxes ?? ''} />
        </label>
        <label>
          {t('catalog.restartGuidance')}
          <textarea name="restart_guidance" defaultValue={layout.restart_guidance} maxLength={2000} />
        </label>
      </ActionForm>
    </details>
  )
}
