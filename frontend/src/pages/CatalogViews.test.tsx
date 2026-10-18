import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { carOf, json, mockApi, renderPage } from '../test-utils'
import { MyCarPanel, TrackPanel, WeatherPanel } from './CatalogViews'

afterEach(() => vi.restoreAllMocks())

describe('briefing panels', () => {
  it('shows my car with its stats, the track facts, and the weather the race announces', async () => {
    mockApi({
      'GET /api/catalog/cars/3': () => json(200, carOf({ id: 3, key: 'acura', name: 'Acura ARX-06', power_hp: 700 })),
      'GET /api/catalog/layouts/9': () =>
        json(200, { id: 9, key: '', name: 'GP', length_m: 4500, pit_boxes: 24, width_m: null, direction: '', has_outline: false, city: 'Monza', country: 'Italia' }),
      'GET /api/catalog/weather': () =>
        json(200, [{ id: 1, key: '3_clear', name: 'Despejado', has_preview: false, facts: { fog_distance: 900, temp_coeff: -0.5 } }]),
    })
    renderPage(
      <>
        <MyCarPanel carId={3} />
        <TrackPanel layoutId={9} trackName="Monza" />
        <WeatherPanel announced="despejado" />
        <WeatherPanel announced="nieve" />
      </>,
      { path: '/', url: '/' },
    )
    expect(await screen.findByText('Acura ARX-06')).toBeInTheDocument()
    expect(screen.getByText('700 hp')).toBeInTheDocument()
    expect(await screen.findByText(/4,5 km/)).toBeInTheDocument()
    expect(screen.getByText('Monza, Italia')).toBeInTheDocument()
    expect(await screen.findAllByRole('heading', { name: 'Despejado' })).toHaveLength(1)
  })
})
