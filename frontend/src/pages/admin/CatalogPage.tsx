import { useState, type FormEvent, type ReactNode } from 'react'
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
import { CatalogEdit, MissingImage } from './CatalogEdit'
import { CarSheet, CarStats, LayoutSheet, LayoutStats } from './CatalogFacts'
import { carFields, layoutFields } from './catalogFields'
import { GameImagesSection } from './GameImagesSection'
import { GameImportDialog } from './GameImportDialog'
import { Breadcrumbs } from '../../components/Breadcrumbs'

type Track = components['schemas']['TrackOut']
type Layout = components['schemas']['LayoutOut']
type Car = components['schemas']['CarOut']

const TABS = ['tracks', 'cars', 'classes', 'images'] as const
type Tab = (typeof TABS)[number]
type Creating = 'track' | 'car' | 'class' | null
type ImageFilter = '' | 'with' | 'without'

const has = (text: string | null | undefined, needle: string) => (text ?? '').toLowerCase().includes(needle)

/** A track matches by its name, a layout name, or a country. The image filter looks at the maps. */
function trackMatches(track: Track, query: string, image: ImageFilter, country: string): boolean {
  const needle = query.trim().toLowerCase()
  const text =
    !needle ||
    has(track.name, needle) ||
    has(track.country, needle) ||
    track.layouts.some((layout) => has(layout.name, needle) || has(layout.country, needle))
  const inCountry = country === '' || (country === 'none' ? !track.country : track.country === country)
  const maps = track.layouts.map((layout) => layout.has_outline)
  const picture =
    image === '' || (image === 'with' ? maps.some(Boolean) : maps.length === 0 || maps.some((set) => !set))
  return text && picture && inCountry
}

/** A car matches by its name or its brand, its class ("none" for no class), and its photo. */
function carMatches(car: Car, classIds: number[], query: string, carClass: string, image: ImageFilter): boolean {
  const needle = query.trim().toLowerCase()
  const text = !needle || has(car.name, needle) || has(car.brand, needle)
  const inClass = carClass === '' || (carClass === 'none' ? classIds.length === 0 : classIds.includes(Number(carClass)))
  const picture = image === '' || (image === 'with') === car.has_preview
  return text && inClass && picture
}

export function CatalogPage() {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const [trackQuery, setTrackQuery] = useState('')
  const [importing, setImporting] = useState(false)
  const [trackImage, setTrackImage] = useState<ImageFilter>('')
  const [trackCountry, setTrackCountry] = useState('')
  const [carQuery, setCarQuery] = useState('')
  const [carClass, setCarClass] = useState('')
  const [carImage, setCarImage] = useState<ImageFilter>('')
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const classes = useLoad(() => api.GET('/api/catalog/classes'), [])
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState<Creating>(null)
  const asked = params.get('tab')
  const tab: Tab = TABS.includes(asked as Tab) ? (asked as Tab) : 'tracks'

  if (!tracks.data || !cars.data || !classes.data) return <Loading failed={tracks.failed || cars.failed || classes.failed} />
  const classList = classes.data
  const classesOf = (carId: number) => classList.filter((item) => item.car_ids.includes(carId))
  const shownTracks = tracks.data.filter((track) => trackMatches(track, trackQuery, trackImage, trackCountry))
  const countries = [...new Set(tracks.data.map((track) => track.country).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  )
  const shownCars = cars.data.filter((car) =>
    carMatches(
      car,
      classesOf(car.id).map((item) => item.id),
      carQuery,
      carClass,
      carImage,
    ),
  )

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
        <div className="page-actions">
          <button type="button" onClick={() => setImporting(true)}>
            <Icon name="download" small />
            {t('gameImport.button')}
          </button>
          {counts[tab] > 0 && createButton(tab)}
        </div>
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
            <>
              <FilterBar
                query={trackQuery}
                onQuery={setTrackQuery}
                placeholder={t('catalogFilter.trackPlaceholder')}
                image={trackImage}
                onImage={setTrackImage}
                count={t('catalogFilter.trackCount', { count: shownTracks.length })}
              >
                <label className="catalog-select-filter">
                  <span className="sr-only">{t('catalogFilter.country')}</span>
                  <select value={trackCountry} onChange={(e) => setTrackCountry(e.target.value)}>
                    <option value="">{t('catalogFilter.allCountries')}</option>
                    {countries.map((country) => (
                      <option key={country} value={country}>
                        {country}
                      </option>
                    ))}
                    <option value="none">{t('catalogFilter.noCountry')}</option>
                  </select>
                </label>
              </FilterBar>
              {shownTracks.length === 0 ? (
                <NoMatch
                  onClear={() => {
                    setTrackQuery('')
                    setTrackImage('')
                    setTrackCountry('')
                  }}
                />
              ) : (
                <div className="track-list">
                  {shownTracks.map((track) => (
                    <TrackCard key={track.id} track={track} onChange={tracks.reload} />
                  ))}
                </div>
              )}
            </>
          ))}

        {tab === 'cars' &&
          (cars.data.length === 0 ? (
            <EmptyState icon="flag" title={t('catalog.noCars')} text={t('catalog.carsEmptyText')}>
              {createButton('cars')}
            </EmptyState>
          ) : (
            <>
              <FilterBar
                query={carQuery}
                onQuery={setCarQuery}
                placeholder={t('catalogFilter.carPlaceholder')}
                image={carImage}
                onImage={setCarImage}
                count={t('catalogFilter.carCount', { count: shownCars.length })}
              />
              {classes.data.length > 0 && (
                <div className="kind-chips" role="group" aria-label={t('catalogFilter.classLabel')}>
                  {[
                    { id: '', name: t('catalogFilter.allClasses') },
                    ...classes.data.map((item) => ({ id: String(item.id), name: item.name })),
                    { id: 'none', name: t('catalog.noClass') },
                  ].map((option) => (
                    <button
                      key={option.id || 'all'}
                      type="button"
                      className="kind-chip"
                      aria-pressed={carClass === option.id}
                      onClick={() => setCarClass(option.id)}
                    >
                      {option.name}
                    </button>
                  ))}
                </div>
              )}
              {shownCars.length === 0 ? (
                <NoMatch
                  onClear={() => {
                    setCarQuery('')
                    setCarClass('')
                    setCarImage('')
                  }}
                />
              ) : (
                <ul className="catalog-grid">
                  {shownCars.map((car) => (
                    <CarCard
                      key={car.id}
                      car={car}
                      classes={classesOf(car.id).map((item) => item.name)}
                      onChange={cars.reload}
                    />
                  ))}
                </ul>
              )}
            </>
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
              body: {
                key: String(form.get('key')),
                name: String(form.get('name')),
                country: String(form.get('country') ?? '').trim(),
              },
            })
            if (!error) {
              setCreating(null)
              tracks.reload()
            }
            return error
          }}
        >
          <KeyAndName />
          <label>
            {t('catalogEdit.country')}
            <input name="country" maxLength={100} />
          </label>
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
      <GameImportDialog
        open={importing}
        onClose={() => setImporting(false)}
        onImported={reloadImages}
        knownCars={cars.data?.map((car) => car.key) ?? []}
        knownTracks={tracks.data?.map((track) => track.key) ?? []}
      />
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
          <h2 className="track-name" title={track.name}>
            {track.name}
          </h2>
          {track.country && <p className="muted">{track.country}</p>}
        </div>
        <span className="muted track-count">{t('catalog.layoutCount', { count: track.layouts.length })}</span>
        <CatalogEdit
          name={track.name}
          country={track.country}
          base={`/api/catalog/tracks/${track.id}`}
          onChange={onChange}
        />
      </header>
      {track.layouts.length === 0 ? (
        <p className="muted">{t('catalog.noLayouts')}</p>
      ) : (
        <ul className="catalog-grid layout-grid">
          {track.layouts.map((layout) => (
            <LayoutCard key={layout.id} layout={layout} onSaved={onChange} />
          ))}
        </ul>
      )}
      <AddLayout track={track} onCreated={onChange} />
    </article>
  )
}

function LayoutCard({ layout, onSaved }: { layout: Layout; onSaved: () => void }) {
  const { t } = useTranslation()
  const base = `/api/catalog/layouts/${layout.id}`
  // A new picture keeps its address, so the version makes the browser load it again.
  const [version, setVersion] = useState(0)
  const changed = () => {
    setVersion((v) => v + 1)
    onSaved()
  }
  return (
    <li className="catalog-card">
      <div className="catalog-media track">
        {layout.has_outline ? (
          <img src={`${base}/images/outline?v=${version}`} alt="" />
        ) : (
          <MissingImage base={base} kind="outline" onChange={changed} />
        )}
      </div>
      <div className="catalog-body">
        <div className="catalog-title">
          <h3 title={layout.name}>{layout.name}</h3>
          <CatalogEdit
            name={layout.name}
            fields={layoutFields(layout, t)}
            base={base}
            images={[
              { kind: 'outline', set: layout.has_outline },
              { kind: 'preview', set: layout.has_preview },
            ]}
            onChange={changed}
          />
        </div>
        {(layout.city || layout.country) && (
          <p className="muted">{[layout.city, layout.country].filter(Boolean).join(', ')}</p>
        )}
        <LayoutStats layout={layout} />
        <LayoutSheet layout={layout} />
        <GuidanceForm layout={layout} onSaved={onSaved} />
      </div>
    </li>
  )
}

function CarCard({ car, classes, onChange }: { car: Car; classes: string[]; onChange: () => void }) {
  const { t } = useTranslation()
  const base = `/api/catalog/cars/${car.id}`
  // A new picture keeps its address, so the version makes the browser load it again.
  const [version, setVersion] = useState(0)
  const changed = () => {
    setVersion((v) => v + 1)
    onChange()
  }
  return (
    <li className="catalog-card">
      <div className="catalog-media car">
        {car.has_preview ? (
          <img src={`${base}/images/preview?v=${version}`} alt="" />
        ) : (
          <MissingImage base={base} kind="preview" onChange={changed} />
        )}
        {car.has_badge && <img className="catalog-badge" src={`${base}/images/badge?v=${version}`} alt="" />}
      </div>
      <div className="catalog-body">
        <div className="catalog-title">
          <h3 title={car.name}>{car.name}</h3>
          <CatalogEdit
            name={car.name}
            fields={carFields(car, t)}
            base={base}
            images={[
              { kind: 'preview', set: car.has_preview },
              { kind: 'badge', set: car.has_badge },
            ]}
            onChange={changed}
          />
        </div>
        <p className="car-classes">
          {classes.length > 0 ? (
            classes.map((name) => (
              <span key={name} className="badge">
                {name}
              </span>
            ))
          ) : (
            <span className="muted">{t('catalog.noClass')}</span>
          )}
        </p>
        {(car.brand || car.country || car.year) && (
          <p className="muted">{[car.brand, car.country, car.year].filter(Boolean).join(' · ')}</p>
        )}
        <CarStats car={car} />
        <CarSheet car={car} />
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

/** The search box, the image filter, and the count of a catalog list. */
function FilterBar({
  query,
  onQuery,
  placeholder,
  image,
  onImage,
  count,
  children,
}: {
  children?: ReactNode
  query: string
  onQuery: (value: string) => void
  placeholder: string
  image: ImageFilter
  onImage: (value: ImageFilter) => void
  count: string
}) {
  const { t } = useTranslation()
  return (
    <div className="table-tools catalog-filters">
      <label className="search-field">
        <span className="sr-only">{t('catalogFilter.search')}</span>
        <Icon name="search" small />
        <input type="search" value={query} placeholder={placeholder} onChange={(e) => onQuery(e.target.value)} />
      </label>
      {children}
      <label className="catalog-select-filter">
        <span className="sr-only">{t('catalogFilter.image')}</span>
        <select value={image} onChange={(e) => onImage(e.target.value as ImageFilter)}>
          <option value="">{t('catalogFilter.images.all')}</option>
          <option value="with">{t('catalogFilter.images.with')}</option>
          <option value="without">{t('catalogFilter.images.without')}</option>
        </select>
      </label>
      <span className="muted">{count}</span>
    </div>
  )
}

function NoMatch({ onClear }: { onClear: () => void }) {
  const { t } = useTranslation()
  return (
    <p className="muted catalog-no-match">
      {t('catalogFilter.noMatch')}{' '}
      <button type="button" className="link" onClick={onClear}>
        {t('catalogFilter.clear')}
      </button>
    </p>
  )
}
