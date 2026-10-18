import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { CarTyres } from '../components/CarTyres'
import { useLoad } from '../lib/useLoad'
import { CarDetails, SourceBadge } from './admin/CarDetails'
import { CarStats } from './admin/CatalogFacts'

type Car = components['schemas']['CarOut']
type Track = components['schemas']['TrackOut']
type Layout = components['schemas']['LayoutOut']
type Weather = components['schemas']['WeatherOut']

/** The facts of a layout in one line: length, width, pit boxes, direction. */
function layoutFacts(layout: Layout, language: string, t: TFunction): string {
  const number = new Intl.NumberFormat(language, { maximumFractionDigits: 2 })
  return [
    layout.length_m ? `${number.format(layout.length_m / 1000)} km` : '',
    layout.width_m ? `${layout.width_m} m` : '',
    layout.pit_boxes ? t('catalog.pitBoxes', { count: layout.pit_boxes }) : '',
    layout.direction ? t(`facts.directions.${layout.direction}`, { defaultValue: '' }) : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

/** A car for a pilot: the picture, the main numbers, the tyres, and the skins. No editing. */
export function PilotCarCard({ car }: { car: Car }) {
  return (
    <li className="catalog-card">
      <div className="catalog-media car">
        {car.has_preview && <img src={`/api/catalog/cars/${car.id}/images/preview`} alt="" loading="lazy" />}
        {car.has_badge && <img className="catalog-badge" src={`/api/catalog/cars/${car.id}/images/badge`} alt="" loading="lazy" />}
      </div>
      <div className="catalog-body">
        <h3 title={car.name}>{car.name}</h3>
        <p className="car-classes">
          <SourceBadge car={car} />
          {(car.tags ?? []).slice(0, 3).map((tag) => (
            <span key={tag} className="badge">
              {tag}
            </span>
          ))}
        </p>
        {(car.brand || car.country || car.year) && <p className="muted">{[car.brand, car.country, car.year].filter(Boolean).join(' · ')}</p>}
        <CarStats car={car} />
        <CarDetails car={car} />
      </div>
    </li>
  )
}

/** A track for a pilot: its name and country once, then one compact row for each layout. A
 * track with a single layout is the same card with one row. */
export function TrackInfo({ track }: { track: Track }) {
  const { t, i18n } = useTranslation()
  const place = [track.country, ...new Set(track.layouts.map((l) => l.city).filter(Boolean))].filter(Boolean).join(' · ')
  return (
    <li className="card track-info">
      <header>
        <h3 title={track.name}>{track.name}</h3>
        {place && <p className="muted">{place}</p>}
      </header>
      <ul className="track-layouts">
        {track.layouts.map((layout) => (
          <li key={layout.id}>
            <div className="catalog-media track layout-thumb">
              {layout.has_outline && <img src={`/api/catalog/layouts/${layout.id}/images/outline`} alt="" loading="lazy" />}
            </div>
            <span>
              <b>{layout.name || layout.key || t('garage.mainLayout')}</b>
              <span className="muted">{layoutFacts(layout, i18n.language, t)}</span>
            </span>
          </li>
        ))}
      </ul>
    </li>
  )
}

/** A weather preset: the picture, the name, and the temperature and wind numbers of the game. */
export function WeatherInfo({ weather }: { weather: Weather }) {
  const { t } = useTranslation()
  const facts = weather.facts as Record<string, number | boolean | undefined>
  const rows = [
    facts.cloud_cover !== undefined && [t('weather.cloudCover'), `${Math.round(Number(facts.cloud_cover) * 100)} %`],
    facts.fog_distance !== undefined && [t('weather.fogDistance'), `${facts.fog_distance} m`],
    facts.temp_coeff !== undefined && [t('weather.tempCoeff'), `${Number(facts.temp_coeff) > 0 ? '+' : ''}${facts.temp_coeff}`],
    facts.lights_forced && [t('weather.lightsForced'), t('weather.yes')],
  ].filter((row): row is string[] => Array.isArray(row))
  return (
    <li className="catalog-card">
      <div className="catalog-media car">
        {weather.has_preview && <img src={`/api/catalog/weather/${weather.id}/preview`} alt="" loading="lazy" />}
      </div>
      <div className="catalog-body">
        <h3 title={weather.name}>{weather.name}</h3>
        {rows.length > 0 && (
          <dl className="catalog-stats">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {facts.temp_coeff !== undefined && <p className="muted">{t('weather.tempHelp')}</p>}
      </div>
    </li>
  )
}

/** The car of the pilot in a race: the numbers and the tyres. Shows nothing while it loads. */
export function MyCarPanel({ carId }: { carId: number }) {
  const { t } = useTranslation()
  const car = useLoad(() => api.GET('/api/catalog/cars/{car_id}', { params: { path: { car_id: carId } } }), [carId])
  if (!car.data) return null
  return (
    <div className="card briefing-catalog">
      <h3>{t('briefing.myCar')}</h3>
      <p>
        <strong>{car.data.name}</strong>
      </p>
      <CarStats car={car.data} />
      {car.data.tyres.length > 0 && (
        <details>
          <summary>{t('carDetail.tyres', { count: car.data.tyres.length })}</summary>
          <CarTyres tyres={car.data.tyres} />
        </details>
      )}
    </div>
  )
}

/** The layout of the race: the map and its numbers. */
export function TrackPanel({ layoutId, trackName }: { layoutId: number; trackName: string }) {
  const { t, i18n } = useTranslation()
  const layout = useLoad(() => api.GET('/api/catalog/layouts/{layout_id}', { params: { path: { layout_id: layoutId } } }), [layoutId])
  if (!layout.data) return null
  const facts = layoutFacts(layout.data, i18n.language, t)
  return (
    <div className="card briefing-catalog">
      <h3>{t('briefing.theTrack')}</h3>
      <div className="catalog-media track layout-thumb wide">
        {layout.data.has_outline && <img src={`/api/catalog/layouts/${layout.data.id}/images/outline`} alt="" />}
      </div>
      <p>
        <strong>{trackName}</strong>
        {facts && <span className="muted"> · {facts}</span>}
      </p>
      {(layout.data.city || layout.data.country) && <p className="muted">{[layout.data.city, layout.data.country].filter(Boolean).join(', ')}</p>}
    </div>
  )
}

/** The expected weather: the preset that the announced weather names, when the catalog has it. */
export function WeatherPanel({ announced }: { announced: string }) {
  const { t } = useTranslation()
  const presets = useLoad(() => api.GET('/api/catalog/weather'), [])
  const wanted = announced.trim().toLowerCase()
  const found = wanted ? (presets.data ?? []).find((w) => w.key.toLowerCase() === wanted || w.name.toLowerCase() === wanted) : undefined
  if (!found) return null
  return (
    <div className="card briefing-catalog">
      <h3>{t('briefing.expectedWeather')}</h3>
      <ul className="catalog-grid">
        <WeatherInfo weather={found} />
      </ul>
    </div>
  )
}
