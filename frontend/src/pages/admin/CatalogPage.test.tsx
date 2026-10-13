import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { CatalogPage } from './CatalogPage'

afterEach(() => vi.restoreAllMocks())

const layout = (id: number, name: string, key: string, outline = false) => ({
  id, name, key, has_outline: outline, length_m: 6400, country: 'Escocia', pit_boxes: 24,
  restart_guidance: '', first_lap_cutoff: '',
})
const tracks = [
  { id: 1, key: 'ks_highlands', name: 'Highlands', layouts: [layout(10, 'Long', 'layout_long', true), layout(11, 'Short', 'layout_short')] },
  { id: 2, key: 'magione', name: 'Magione', layouts: [] },
]
const cars = [{ id: 1, key: 'acura', name: 'Acura', has_preview: false, has_badge: false, brand: 'Acura', author: '' }]

function routes(extra = {}) {
  return {
    'GET /api/catalog/tracks': () => json(200, tracks),
    'GET /api/catalog/cars': () => json(200, cars),
    'GET /api/catalog/classes': () => json(200, []),
    ...extra,
  }
}

describe('CatalogPage', () => {
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
    expect(within(highlands).getAllByRole('listitem').map((li) => li.querySelector('.catalog-body > h3')?.textContent)).toEqual(['Long', 'Short'])
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
