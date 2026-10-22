import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { carOf, json, mockApi, renderPage } from '../../test-utils'
import { CarClassesSection } from './CarClassesSection'

afterEach(() => vi.restoreAllMocks())

const cars = [
  carOf({ id: 1, key: 'acura', name: 'Acura', has_preview: true }),
  carOf({ id: 2, key: 'cadillac', name: 'Cadillac' }),
]
const gt = {
  id: 5, name: 'LMDh', parent_id: null, car_ids: [1],
  history: [{ car_id: 2, car_name: 'Cadillac', valid_from: '2026-01-01', valid_to: '2026-06-30', reason: 'BoP' }],
}

function show(calls: Parameters<typeof mockApi>[0]) {
  const log = mockApi(calls)
  const onSaved = vi.fn()
  const view = renderPage(
    <CarClassesSection cars={cars} classes={[gt]} onSaved={onSaved} onCarsChanged={vi.fn()} />,
    { path: '/admin/catalog', url: '/admin/catalog' },
  )
  return { log, onSaved, view }
}

describe('CarClassesSection', () => {
  it('shows a card with the picture of each car of the class', async () => {
    const { view } = show({})
    expect(await screen.findByText('Acura')).toBeInTheDocument()
    expect(screen.getByText('1 auto')).toBeInTheDocument()
    expect(view.container.querySelector('img[src^="/api/catalog/cars/1/images/preview"]')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Acciones de Acura' })).toBeInTheDocument()
  })

  it('changes the cars from the class menu, with a reason', async () => {
    const { log, onSaved } = show({
      'PUT /api/catalog/classes/5/cars': () => json(200, { ...gt, car_ids: [1, 2] }),
    })
    await userEvent.click(screen.getByText('Historial'))
    expect(screen.getByText('Cadillac: 2026-01-01 → 2026-06-30 (BoP)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Más opciones de LMDh' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar autos' }))
    await userEvent.click(screen.getByRole('button', { name: 'Agregar Cadillac' }))
    await userEvent.type(screen.getByLabelText('Motivo del cambio'), 'Nueva BoP')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() =>
      expect(log.find((c) => c.key === 'PUT /api/catalog/classes/5/cars')!.body).toEqual({ car_ids: [1, 2], reason: 'Nueva BoP' }),
    )
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('edits the class name', async () => {
    const { log } = show({
      'PATCH /api/catalog/classes/5': () => json(200, { ...gt, name: 'Hypercar' }),
    })
    await userEvent.click(screen.getByRole('button', { name: 'Más opciones de LMDh' }))
    await userEvent.click(screen.getByRole('button', { name: 'Editar clase' }))
    const name = screen.getByLabelText('Nombre')
    await userEvent.clear(name)
    await userEvent.type(name, 'Hypercar')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() =>
      expect(log.find((c) => c.key === 'PATCH /api/catalog/classes/5')!.body).toEqual({ name: 'Hypercar', parent_id: null }),
    )
  })

  it('removes a car from the class with the car menu', async () => {
    const { log } = show({
      'PUT /api/catalog/classes/5/cars': () => json(200, { ...gt, car_ids: [] }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await userEvent.click(screen.getByRole('button', { name: 'Acciones de Acura' }))
    await userEvent.click(screen.getByRole('button', { name: 'Quitar de la clase' }))
    await vi.waitFor(() =>
      expect(log.find((c) => c.key === 'PUT /api/catalog/classes/5/cars')!.body).toEqual({ car_ids: [], reason: '' }),
    )
  })

  it('shows a subclass inside its class and adds a new subclass', async () => {
    const eighties = { id: 7, name: '80s F1', parent_id: 6, car_ids: [2], history: [] }
    const f1 = { id: 6, name: 'F1', parent_id: null, car_ids: [], history: [] }
    const log = mockApi({ 'POST /api/catalog/classes': () => json(201, { ...eighties, id: 8, name: 'Early F1' }) })
    const { container } = renderPage(
      <CarClassesSection cars={cars} classes={[f1, eighties]} onSaved={vi.fn()} onCarsChanged={vi.fn()} />,
      { path: '/admin/catalog', url: '/admin/catalog' },
    )
    expect(await screen.findByText('0 autos · 1 subclase')).toBeInTheDocument()
    expect(container.querySelector('.subclass-card h3')!.textContent).toContain('80s F1')
    await userEvent.click(screen.getByRole('button', { name: 'Más opciones de F1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Nueva subclase' }))
    await userEvent.type(screen.getByLabelText('Nombre'), 'Early F1')
    await userEvent.click(screen.getByRole('button', { name: 'Crear' }))
    await vi.waitFor(() =>
      expect(log.find((c) => c.key === 'POST /api/catalog/classes')!.body).toEqual({ name: 'Early F1', parent_id: 6 }),
    )
  })
})
