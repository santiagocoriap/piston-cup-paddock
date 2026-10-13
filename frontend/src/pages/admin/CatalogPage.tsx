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
      {tracks.data.length === 0 && <p className="muted">{t('catalog.noTracks')}</p>}
      <ul className="catalog-grid">
        {tracks.data.flatMap((track) =>
          track.layouts.map((layout) => (
            <li key={layout.id} className="catalog-card">
              <div className="catalog-media track">
                {layout.has_outline ? (
                  <img src={`/api/catalog/layouts/${layout.id}/images/outline`} alt="" />
                ) : (
                  <span className="catalog-missing">{t('catalog.noImage')}</span>
                )}
              </div>
              <div className="catalog-body">
                <h3>
                  {track.name} · {layout.name}
                </h3>
                <p className="mono muted">
                  {track.key}
                  {layout.key && `/${layout.key}`}
                </p>
                <p className="muted">
                  {[
                    layout.length_m ? `${(layout.length_m / 1000).toFixed(3)} km` : null,
                    layout.country || null,
                    layout.pit_boxes ? t('catalog.pitBoxes', { count: layout.pit_boxes }) : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
                <GuidanceForm layout={layout} onSaved={tracks.reload} />
              </div>
            </li>
          )),
        )}
      </ul>

      <h2>{t('catalog.cars')}</h2>
      {cars.data.length === 0 && <p className="muted">{t('catalog.noCars')}</p>}
      <ul className="catalog-grid">
        {cars.data.map((car) => (
          <li key={car.id} className="catalog-card">
            <div className="catalog-media car">
              {car.has_preview ? (
                <img src={`/api/catalog/cars/${car.id}/images/preview`} alt="" />
              ) : (
                <span className="catalog-missing">{t('catalog.noImage')}</span>
              )}
              {car.has_badge && (
                <img className="catalog-badge" src={`/api/catalog/cars/${car.id}/images/badge`} alt="" />
              )}
            </div>
            <div className="catalog-body">
              <h3>{car.name}</h3>
              <p className="mono muted">{car.key}</p>
              {(car.brand || car.author) && (
                <p className="muted">
                  {[car.brand, car.author ? t('catalog.images.author', { author: car.author }) : null]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              )}
            </div>
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
