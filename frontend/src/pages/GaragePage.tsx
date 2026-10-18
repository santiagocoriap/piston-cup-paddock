import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { EmptyState } from '../components/EmptyState'
import { Loading } from '../components/Layout'
import { Tabs } from '../components/Tabs'
import { useLoad } from '../lib/useLoad'
import { panelId, tabId } from '../lib/tabs'
import { PilotCarCard, TrackInfo, WeatherInfo } from './CatalogViews'

const TABS = ['cars', 'tracks', 'weather'] as const
type Tab = (typeof TABS)[number]

/** "Autos y pistas": what a pilot can look up before a race. Cars with their numbers, tyres and
 * skins, tracks with their layouts, and the weather presets. Read only. */
export function GaragePage() {
  const { t } = useTranslation()
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const weather = useLoad(() => api.GET('/api/catalog/weather'), [])
  const [tab, setTab] = useState<Tab>('cars')
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [tag, setTag] = useState('')
  if (!cars.data || !tracks.data || !weather.data) return <Loading failed={cars.failed || tracks.failed || weather.failed} />

  const words = query.trim().toLowerCase()
  const match = (...texts: (string | undefined)[]) => !words || texts.join(' ').toLowerCase().includes(words)
  const tagCounts = new Map<string, number>()
  for (const car of cars.data) for (const name of new Set(car.tags ?? [])) tagCounts.set(name, (tagCounts.get(name) ?? 0) + 1)
  const tagList = [...tagCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  const shownCars = cars.data.filter(
    (car) => match(car.name, car.brand, car.country) && (!source || car.source === source) && (!tag || car.tags?.includes(tag)),
  )
  const shownTracks = tracks.data.filter((track) => track.layouts.length > 0 && match(track.name, track.country, ...track.layouts.map((l) => `${l.name} ${l.city}`)))
  const shownWeather = weather.data.filter((preset) => match(preset.name, preset.key))
  const counts: Record<Tab, number> = { cars: shownCars.length, tracks: shownTracks.length, weather: shownWeather.length }

  return (
    <section className="garage" aria-labelledby="garage-title">
      <header className="page-head">
        <h1 id="garage-title">{t('garage.title')}</h1>
        <p className="muted">{t('garage.help')}</p>
      </header>
      <Tabs
        label={t('garage.sections')}
        idPrefix="garage"
        active={tab}
        onChange={(next) => setTab(next as Tab)}
        tabs={TABS.map((id) => ({ id, label: t(`garage.${id}`), count: counts[id] }))}
      />
      <div className="table-tools catalog-filters">
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('garage.search')} aria-label={t('garage.search')} />
        {tab === 'cars' && (
          <>
            <select value={source} onChange={(e) => setSource(e.target.value)} aria-label={t('carDetail.sourceLabel')}>
              <option value="">{t('carDetail.allSources')}</option>
              {(['base', 'dlc', 'mod'] as const).map((value) => (
                <option key={value} value={value}>
                  {t(`carDetail.source.${value}`)}
                </option>
              ))}
            </select>
            {tagList.length > 0 && (
              <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label={t('carDetail.tagLabel')}>
                <option value="">{t('carDetail.allTags')}</option>
                {tagList.map(([name, count]) => (
                  <option key={name} value={name}>
                    {name} ({count})
                  </option>
                ))}
              </select>
            )}
          </>
        )}
      </div>
      <div id={panelId('garage', tab)} role="tabpanel" aria-labelledby={tabId('garage', tab)}>
        {counts[tab] === 0 ? (
          <EmptyState icon="map" title={t('garage.none')} text={t('garage.noneText')} />
        ) : (
          <ul className={tab === 'tracks' ? 'garage-tracks' : 'catalog-grid'}>
            {tab === 'cars' && shownCars.map((car) => <PilotCarCard key={car.id} car={car} />)}
            {tab === 'tracks' && shownTracks.map((track) => <TrackInfo key={track.id} track={track} />)}
            {tab === 'weather' && shownWeather.map((preset) => <WeatherInfo key={preset.id} weather={preset} />)}
          </ul>
        )}
      </div>
    </section>
  )
}
