import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { carOf, json, mockApi, renderPage } from '../../test-utils'
import { CatalogPage } from './CatalogPage'

afterEach(() => vi.restoreAllMocks())

const layout = (id: number, name: string, key: string, outline = false) => ({
  id, name, key, has_outline: outline, length_m: 6400, country: 'Escocia', pit_boxes: 24,
  restart_guidance: '', first_lap_cutoff: '',
})
const tracks = [
  { id: 1, key: 'ks_highlands', name: 'Highlands', country: 'Escocia', layouts: [layout(10, 'Long', 'layout_long', true), layout(11, 'Short', 'layout_short')] },
  { id: 2, key: 'magione', name: 'Magione', country: 'Italia', layouts: [] },
]
const cars = [carOf({ id: 1, key: 'acura', name: 'Acura', brand: 'Acura' })]

function routes(extra = {}) {
  return {
    'GET /api/catalog/tracks': () => json(200, tracks),
    'GET /api/catalog/cars': () => json(200, cars),
    'GET /api/catalog/classes': () => json(200, []),
    ...extra,
  }
}

describe('CatalogPage', () => {
  it('filters the tracks by country and edits the country of a track', async () => {
    const calls = mockApi(routes({ 'PATCH /api/catalog/tracks/2': () => json(200, { ...tracks[1], country: 'Italy' }) }))
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'País' }), 'Italia')
    expect(screen.getByText('1 pista')).toBeInTheDocument()
    const magione = screen.getByRole('article', { name: 'Magione' })
    expect(magione).toHaveTextContent('Italia')
    expect(screen.queryByRole('article', { name: 'Highlands' })).not.toBeInTheDocument()

    await userEvent.click(within(magione).getByRole('button', { name: 'Acciones de Magione' }))
    await userEvent.click(screen.getByRole('button', { name: 'Editar el nombre y el país' }))
    const form = await screen.findByRole('form', { name: 'Editar el nombre y el país' })
    expect(within(form).getByLabelText('País')).toHaveValue('Italia')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'PATCH /api/catalog/tracks/2')).toBe(true))
  })

  it('filters the cars by source and tag, and shows the skins and the tyres of a car', async () => {
    const tyre = { index: 0, name: 'Slick Soft', short_name: 'S', front: { width: 0.3, radius: 0.34, pressure_ideal: 26 }, rear: { width: 0.31, radius: 0.355 } }
    mockApi(
      routes({
        'GET /api/catalog/cars': () =>
          json(200, [
            carOf({ id: 1, key: 'ks_ferrari', name: 'Ferrari 488', source: 'dlc', tags: ['gt3', 'italy'], tyres: [tyre], skins: [{ id: 7, key: '00_red', name: 'Rosso', driver_name: '', team: '', number: '', has_preview: true }] }),
            carOf({ id: 2, key: 'trr_bmw', name: 'BMW M4', source: 'mod', tags: ['gt3'] }),
            carOf({ id: 3, key: 'ks_miata', name: 'Miata', source: 'base', tags: ['street'] }),
          ]),
      }),
    )
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog?tab=cars' })
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Origen' }), 'dlc')
    expect(screen.getByText('1 auto')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ferrari 488' })).toBeInTheDocument()
    expect(screen.getByText('1 skin')).toBeInTheDocument()
    expect(screen.getByText('1 compuesto de neumático')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Slick Soft/ })).toHaveTextContent('300/R340')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Origen' }), '')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Etiqueta' }), 'gt3')
    expect(screen.getByText('2 autos')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Miata' })).not.toBeInTheDocument()
  })

  it('filters the tracks by name and the cars by class and photo', async () => {
    mockApi(
      routes({
        'GET /api/catalog/cars': () =>
          json(200, [...cars, carOf({ id: 2, key: 'bmw', name: 'BMW M4', has_preview: true, brand: 'BMW' })]),
        'GET /api/catalog/classes': () => json(200, [{ id: 5, name: 'GT3', car_ids: [2], history: [] }]),
      }),
    )
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    await userEvent.type(await screen.findByPlaceholderText('Buscar pista, trazado o país'), 'escocia')
    expect(screen.getByText('1 pista')).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Magione' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByPlaceholderText('Buscar pista, trazado o país'), 'zzz')
    await userEvent.click(screen.getByRole('button', { name: 'Quitar los filtros' }))
    expect(screen.getByText('2 pistas')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Autos/ }))
    await userEvent.click(screen.getByRole('button', { name: 'GT3' }))
    expect(screen.getByText('1 auto')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'BMW M4' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Sin clase' }))
    await userEvent.selectOptions(screen.getByLabelText('Imagen'), 'without')
    expect(screen.getByRole('heading', { name: 'Acura' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'BMW M4' })).not.toBeInTheDocument()
  })

  it('edits the data of a car and uploads its photo from the card', async () => {
    const calls = mockApi(
      routes({
        'PATCH /api/catalog/cars/1': () => json(200, { ...cars[0], name: 'Acura ARX-06' }),
        'POST /api/catalog/cars/1/images/preview': () => json(200, { ...cars[0], has_preview: true }),
      }),
    )
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog?tab=cars' })
    await userEvent.click(await screen.findByRole('button', { name: 'Acciones de Acura' }))
    await userEvent.click(screen.getByRole('button', { name: 'Editar los datos' }))
    const form = await screen.findByRole('form', { name: 'Editar los datos' })
    await userEvent.clear(within(form).getByLabelText('Nombre'))
    await userEvent.type(within(form).getByLabelText('Nombre'), 'Acura ARX-06')
    await userEvent.type(within(form).getByLabelText('Potencia (hp)'), '584')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'PATCH /api/catalog/cars/1')).toBe(true))

    // The empty picture box has its own upload button.
    const photo = new File(['png'], 'acura.png', { type: 'image/png' })
    await userEvent.upload(screen.getAllByLabelText('Subir la foto')[0], photo)
    await vi.waitFor(() =>
      expect(calls.find((c) => c.key === 'POST /api/catalog/cars/1/images/preview')?.body).toEqual({ file: '[form field]' }),
    )
  })

  it('shows tabs with counts and the missing image count', async () => {
    mockApi(routes())
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    const tabs = await screen.findByRole('tablist', { name: 'Secciones del catálogo' })
    expect(within(tabs).getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Pistas2', 'Autos1', 'Clases de autos0', 'Imágenes2'])
    expect(within(tabs).getByRole('tab', { name: /Pistas/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows a track with no layout, so a new track is easy to find', async () => {
    mockApi(routes())
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    const magione = await screen.findByRole('article', { name: 'Magione' })
    expect(magione).toHaveTextContent('0 trazados')
    expect(magione).toHaveTextContent('Esta pista todavía no tiene trazados.')
    const highlands = screen.getByRole('article', { name: 'Highlands' })
    expect(within(highlands).getAllByRole('listitem').map((li) => li.querySelector('.catalog-title > h3')?.textContent)).toEqual(['Long', 'Short'])
  })

  it('adds a layout inside its track', async () => {
    const calls = mockApi(routes({ 'POST /api/catalog/tracks/2/layouts': () => json(201, layout(12, 'GP', '')) }))
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    const magione = await screen.findByRole('article', { name: 'Magione' })
    await userEvent.click(within(magione).getByRole('button', { name: 'Nuevo trazado' }))
    const form = within(magione).getByRole('form', { name: 'Nuevo trazado: Magione' })
    await userEvent.type(within(form).getByLabelText('Nombre'), 'GP')
    await userEvent.click(within(form).getByRole('button', { name: 'Crear' }))
    expect(await within(magione).findByRole('status')).toHaveTextContent('Trazado «GP» creado.')
    expect(calls.find((c) => c.key === 'POST /api/catalog/tracks/2/layouts')!.body).toEqual({ key: '', name: 'GP' })
  })

  it('changes the header button with the tab and creates a car in a dialog', async () => {
    const calls = mockApi(routes({ 'POST /api/catalog/cars': () => json(201, cars[0]) }))
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    expect(await screen.findByRole('button', { name: 'Nueva pista' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: /Autos/ }))
    expect(screen.queryByRole('button', { name: 'Nueva pista' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo auto' }))
    const dialog = screen.getByRole('dialog', { name: 'Nuevo auto' })
    await userEvent.type(within(dialog).getByLabelText('Carpeta en AC'), 'bmw')
    await userEvent.type(within(dialog).getByLabelText('Nombre'), 'BMW')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Crear' }))
    await vi.waitFor(() => expect(dialog).not.toHaveAttribute('open'))
    expect(calls.find((c) => c.key === 'POST /api/catalog/cars')!.body).toEqual({ key: 'bmw', name: 'BMW' })
  })

  it('moves between tabs with the arrow keys', async () => {
    mockApi(routes())
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog' })
    const tracksTab = await screen.findByRole('tab', { name: /Pistas/ })
    tracksTab.focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(screen.getByRole('tab', { name: /Imágenes/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Imágenes/ })).toHaveFocus()
    expect(screen.getByRole('tabpanel')).toHaveTextContent('2 sin imagen')
  })

  it('shows an empty state for classes with a create button', async () => {
    mockApi(routes())
    renderPage(<CatalogPage />, { path: '/admin/catalog', url: '/admin/catalog?tab=classes' })
    expect(await screen.findByText('Todavía no hay clases.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Nueva clase' })).toHaveLength(1)
  })
})
