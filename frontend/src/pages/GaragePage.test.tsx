import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../i18n'
import { CarTyres } from '../components/CarTyres'
import { carOf, json, mockApi, renderPage } from '../test-utils'
import { GaragePage } from './GaragePage'

afterEach(() => vi.restoreAllMocks())

const wear = (x95: number | null) => ({ curve: [[0, 1], [50, 0.8]], x_95: x95, x_90: null, x_80: 50, end_x: 50, end_grip: 0.8 })
const side = (curve: ReturnType<typeof wear> | null, file = 'a.lut') => ({ width: 0.205, radius: 0.308, pressure_ideal: 32, wear_curve: file, ...(curve ? { wear: curve } : {}) })

describe('CarTyres', () => {
  it('shows the size, the pressure, and where the grip falls under each level', () => {
    const tyres = [
      { index: 0, name: 'Street', short_name: 'ST', front: side(wear(20)), rear: side(wear(20)) },
      { index: 1, name: 'Slick', short_name: 'S', front: side(null), rear: side(null) },
    ] as Parameters<typeof CarTyres>[0]['tyres']
    render(<CarTyres tyres={tyres} />)
    const street = screen.getByText('Street').closest('li')!
    expect(street).toHaveTextContent('205/R308')
    expect(street).toHaveTextContent('32 psi')
    expect(within(street).getByText(/bajo 95 % a 20/)).toBeInTheDocument()
    expect(screen.getByText('Slick').closest('li')).toHaveTextContent('Sin datos de desgaste.')
  })
})

describe('GaragePage', () => {
  it('lists cars, tracks as one card with their layouts, and weather, with a search', async () => {
    mockApi({
      'GET /api/catalog/cars': () => json(200, [carOf({ id: 1, key: 'acura', name: 'Acura', source: 'base' }), carOf({ id: 2, key: 'cad', name: 'Cadillac' })]),
      'GET /api/catalog/tracks': () =>
        json(200, [
          {
            id: 1, key: 'spa', name: 'Spa', country: 'Bélgica',
            layouts: [
              { id: 1, key: '', name: 'GP', length_m: 7004, pit_boxes: 20, has_outline: false, city: '', direction: 'clockwise' },
              { id: 2, key: 'endu', name: 'Endurance', length_m: 7000, pit_boxes: 20, has_outline: false, city: '', direction: '' },
            ],
          },
        ]),
      'GET /api/catalog/weather': () => json(200, [{ id: 1, key: '3_clear', name: 'Clear', has_preview: false, facts: { fog_distance: 900, temp_coeff: -0.5 } }]),
    })
    renderPage(<GaragePage />, { path: '/garage', url: '/garage' })
    expect(await screen.findByRole('heading', { name: 'Acura' })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Origen' }), 'base')
    expect(screen.queryByRole('heading', { name: 'Cadillac' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: /Pistas/ }))
    const spa = screen.getByRole('heading', { name: 'Spa' }).closest('li')!
    expect(spa).toHaveTextContent('Endurance')
    expect(spa).toHaveTextContent('7 km')
    expect(screen.getAllByRole('heading', { name: 'Spa' })).toHaveLength(1)
    await userEvent.click(screen.getByRole('tab', { name: /Clima/ }))
    expect(screen.getByRole('heading', { name: 'Clear' })).toBeInTheDocument()
  })
})
