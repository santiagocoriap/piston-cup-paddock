import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { CarClassesSection } from './CarClassesSection'

afterEach(() => vi.restoreAllMocks())

const noImages = { has_preview: false, has_badge: false, brand: '', author: '' }
const cars = [
  { id: 1, key: 'acura', name: 'Acura', ...noImages },
  { id: 2, key: 'cadillac', name: 'Cadillac', ...noImages },
]

describe('CarClassesSection', () => {
  it('shows the cars of a class and saves a change with a reason', async () => {
    const gt = {
      id: 5, name: 'LMDh', car_ids: [1],
      history: [{ car_id: 2, car_name: 'Cadillac', valid_from: '2026-01-01', valid_to: '2026-06-30', reason: 'BoP' }],
    }
    const calls = mockApi({
      'GET /api/catalog/classes': () => json(200, [gt]),
      'PUT /api/catalog/classes/5/cars': () => json(200, { ...gt, car_ids: [1, 2] }),
    })
    renderPage(<CarClassesSection cars={cars} />, { path: '/admin/catalog', url: '/admin/catalog' })
    expect(await screen.findByText('Acura')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Historial'))
    expect(screen.getByText('Cadillac: 2026-01-01 → 2026-06-30 (BoP)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar autos' }))
    await userEvent.click(screen.getByLabelText('Cadillac'))
    await userEvent.type(screen.getByLabelText('Motivo del cambio'), 'Nueva BoP')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() =>
      expect(calls.find((c) => c.key === 'PUT /api/catalog/classes/5/cars')!.body).toEqual({ car_ids: [1, 2], reason: 'Nueva BoP' }),
    )
  })
})
