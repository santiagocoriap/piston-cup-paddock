import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { Dialog } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { Icon } from '../../components/Icon'
import { Loading } from '../../components/Layout'
import { Tabs } from '../../components/Tabs'
import { errorMessage } from '../../lib/errors'
import { panelId, tabId } from '../../lib/tabs'
import { useLoad } from '../../lib/useLoad'
import { CarClassesSection } from './CarClassesSection'
import { GameImagesSection } from './GameImagesSection'
import { Breadcrumbs } from '../../components/Breadcrumbs'

type Track = components['schemas']['TrackOut']
type Layout = components['schemas']['LayoutOut']
type Car = components['schemas']['CarOut']

const TABS = ['tracks', 'cars', 'classes', 'images'] as const
type Tab = (typeof TABS)[number]
type Creating = 'track' | 'car' | 'class' | null

export function CatalogPage() {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const classes = useLoad(() => api.GET('/api/catalog/classes'), [])
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState<Creating>(null)
  const asked = params.get('tab')
  const tab: Tab = TABS.includes(asked as Tab) ? (asked as Tab) : 'tracks'

  if (!tracks.data || !cars.data || !classes.data) return <Loading failed={tracks.failed || cars.failed || classes.failed} />

  const layouts = tracks.data.flatMap((track) => track.layouts)
  const counts: Record<Tab, number> = {
    tracks: tracks.data.length,
    cars: cars.data.length,
    classes: classes.data.length,
    images: 0,
  }
  const missing = layouts.filter((l) => !l.has_outline).length + cars.data.filter((c) => !c.has_preview).length
  const create: Record<Tab, { kind: Creating; label: string } | null> = {
    tracks: { kind: 'track', label: t('catalog.newTrack') },
    cars: { kind: 'car', label: t('catalog.newCar') },
    classes: { kind: 'class', label: t('classes.new') },
    images: null,
  }
  const createButton = (kind: Tab) => {
    const item = create[kind]
    if (!item) return null
    return (
      <button type="button" onClick={() => setCreating(item.kind)}>
        <Icon name="plus" small />
        {item.label}
      </button>
    )
  }
  const reloadImages = () => {
    tracks.reload()
    cars.reload()
  }

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.catalog') }]} />
      <header className="page-head">
        <div>
          <h1>{t('catalog.title')}</h1>
          <p className="muted">{t('catalog.help')}</p>
        </div>
        {/* With an empty list, the empty state has the button. */}
        {counts[tab] > 0 && <div className="page-actions">{createButton(tab)}</div>}
      </header>

      <Tabs
        label={t('catalog.sections')}
        idPrefix="catalog"
        active={tab}
        onChange={(next) => setParams(next === 'tracks' ? {} : { tab: next }, { replace: true })}
        tabs={[
          { id: 'tracks', label: t('catalog.tracks'), count: counts.tracks },
          { id: 'cars', label: t('catalog.cars'), count: counts.cars },
          { id: 'classes', label: t('classes.title'), count: counts.classes },
          { id: 'images', label: t('catalog.tabImages'), ...(missing > 0 ? { count: missing, warn: true } : {}) },
        ]}
      />

      <div id={panelId('catalog', tab)} role="tabpanel" aria-labelledby={tabId('catalog', tab)}>
        {tab === 'tracks' &&
          (tracks.data.length === 0 ? (
            <EmptyState icon="map" title={t('catalog.noTracks')} text={t('catalog.tracksEmptyText')}>
              {createButton('tracks')}
            </EmptyState>
          ) : (
            <div className="track-list">
              {tracks.data.map((track) => (
                <TrackCard key={track.id} track={track} onChange={tracks.reload} />
              ))}
            </div>
          ))}

        {tab === 'cars' &&
          (cars.data.length === 0 ? (
            <EmptyState icon="flag" title={t('catalog.noCars')} text={t('catalog.carsEmptyText')}>
              {createButton('cars')}
            </EmptyState>
          ) : (
            <ul className="catalog-grid">
              {cars.data.map((car) => (
                <CarCard key={car.id} car={car} />
              ))}
            </ul>
          ))}

        {tab === 'classes' &&
          (classes.data.length === 0 ? (
            <EmptyState icon="layers" title={t('classes.none')} text={t('classes.emptyText')}>
              {createButton('classes')}
            </EmptyState>
          ) : (
            <CarClassesSection cars={cars.data} classes={classes.data} onSaved={classes.reload} />
          ))}

        {tab === 'images' && (
          <>
            {missing > 0 && (
              <p className="muted">
                <Icon name="alert" small /> {t('catalog.missingImages', { count: missing })}
              </p>
            )}
            <GameImagesSection onImported={reloadImages} />
          </>
        )}
      </div>

      <Dialog open={creating === 'track'} title={t('catalog.newTrack')} onClose={() => setCreating(null)}>
        <ActionForm
          title={t('catalog.newTrack')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/catalog/tracks', {
              body: { key: String(form.get('key')), name: String(form.get('name')) },
            })
            if (!error) {
              setCreating(null)
              tracks.reload()
            }
            return error
          }}
        >
          <KeyAndName />
        </ActionForm>
      </Dialog>

      <Dialog open={creating === 'car'} title={t('catalog.newCar')} onClose={() => setCreating(null)}>
        <ActionForm
          title={t('catalog.newCar')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/catalog/cars', {
              body: { key: String(form.get('key')), name: String(form.get('name')) },
            })
            if (!error) {
              setCreating(null)
              cars.reload()
            }
            return error
          }}
        >
          <KeyAndName />
        </ActionForm>
      </Dialog>

      <Dialog open={creating === 'class'} title={t('classes.new')} onClose={() => setCreating(null)}>
        <ActionForm
          title={t('classes.new')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/catalog/classes', { body: { name: String(form.get('name')) } })
            if (!error) {
              setCreating(null)
              classes.reload()
            }
            return error
          }}
        >
          <label>
            {t('classes.name')}
            <input name="name" required maxLength={60} />
          </label>
        </ActionForm>
      </Dialog>
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

/** One track with its layouts. A track with no layout shows too, so a new track is easy to find. */
function TrackCard({ track, onChange }: { track: Track; onChange: () => void }) {
  const { t } = useTranslation()
  return (
    <article className="card track-card" aria-label={track.name}>
      <header className="track-head">
        <span className="track-icon" aria-hidden="true">
          <Icon name="map" />
        </span>
        <div>
          <h2 className="track-name">{track.name}</h2>
          <p className="mono muted">{track.key}</p>
        </div>
        <span className="muted track-count">{t('catalog.layoutCount', { count: track.layouts.length })}</span>
      </header>
      {track.layouts.length === 0 ? (
        <p className="muted">{t('catalog.noLayouts')}</p>
      ) : (
        <ul className="catalog-grid layout-grid">
          {track.layouts.map((layout) => (
            <LayoutCard key={layout.id} track={track} layout={layout} onSaved={onChange} />
          ))}
        </ul>
      )}
      <AddLayout track={track} onCreated={onChange} />
    </article>
  )
}

function LayoutCard({ track, layout, onSaved }: { track: Track; layout: Layout; onSaved: () => void }) {
  const { t } = useTranslation()
  const facts = [
    layout.length_m ? `${(layout.length_m / 1000).toFixed(3)} km` : null,
    layout.country || null,
    layout.pit_boxes ? t('catalog.pitBoxes', { count: layout.pit_boxes }) : null,
  ].filter(Boolean)
  return (
    <li className="catalog-card">
      <div className="catalog-media track">
        {layout.has_outline ? (
          <img src={`/api/catalog/layouts/${layout.id}/images/outline`} alt="" />
        ) : (
          <span className="catalog-missing">{t('catalog.noImage')}</span>
        )}
      </div>
      <div className="catalog-body">
        <h3>{layout.name}</h3>
        <p className="mono muted">
          {track.key}
          {layout.key && `/${layout.key}`}
        </p>
        {facts.length > 0 && <p className="muted">{facts.join(' · ')}</p>}
        <GuidanceForm layout={layout} onSaved={onSaved} />
      </div>
    </li>
  )
}

function CarCard({ car }: { car: Car }) {
  const { t } = useTranslation()
  return (
    <li className="catalog-card">
      <div className="catalog-media car">
        {car.has_preview ? (
          <img src={`/api/catalog/cars/${car.id}/images/preview`} alt="" />
        ) : (
          <span className="catalog-missing">{t('catalog.noImage')}</span>
        )}
        {car.has_badge && <img className="catalog-badge" src={`/api/catalog/cars/${car.id}/images/badge`} alt="" />}
      </div>
      <div className="catalog-body">
        <h3>{car.name}</h3>
        <p className="mono muted">{car.key}</p>
        {(car.brand || car.author) && (
          <p className="muted">
            {[car.brand, car.author ? t('catalog.images.author', { author: car.author }) : null].filter(Boolean).join(' · ')}
          </p>
        )}
      </div>
    </li>
  )
}

/** A dashed "add" row that opens into a small layout form. */
function AddLayout({ track, onCreated }: { track: Track; onCreated: () => void }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name')).trim()
    setBusy(true)
    setError(null)
    const { error: apiError } = await api.POST('/api/catalog/tracks/{track_id}/layouts', {
      params: { path: { track_id: track.id } },
      body: { key: String(form.get('key') ?? '').trim(), name },
    })
    setBusy(false)
    if (apiError) return setError(errorMessage(t, apiError))
    setEditing(false)
    setCreated(name)
    onCreated()
  }

  return (
    <div className="inline-add">
      {created && (
        <p role="status" className="notice-ok">
          <Icon name="check" small />
          {t('catalog.layoutCreated', { name: created })}
        </p>
      )}
      {editing ? (
        <form className="inline-add-form" onSubmit={submit} aria-label={t('catalog.newLayoutFor', { name: track.name })}>
          <label>
            {t('common.key')}
            <input name="key" maxLength={100} placeholder={t('catalog.layoutKeyHint')} autoFocus />
          </label>
          <label>
            {t('common.name')}
            <input name="name" required maxLength={200} />
          </label>
          <div className="inline-add-actions">
            <button type="submit" disabled={busy}>
              {t('common.create')}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setEditing(false)
                setError(null)
              }}
            >
              {t('common.cancel')}
            </button>
          </div>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </form>
      ) : (
        <button
          type="button"
          className="add-row"
          onClick={() => {
            setEditing(true)
            setCreated(null)
          }}
        >
          <Icon name="plus" small />
          {t('catalog.newLayout')}
        </button>
      )}
    </div>
  )
}

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
