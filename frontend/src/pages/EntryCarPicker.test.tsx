import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { EntryCarPicker } from './EntryCarPicker'

afterEach(() => vi.restoreAllMocks())

const car = (id: number, name: string) => ({
  id, key: name.toLowerCase(), name, has_preview: false, has_badge: false, brand: '', author: '', game_class: '',
  country: '', year: null, power_hp: null, torque_nm: null,
})
const entry = {
  id: 7, driver_id: 2, driver_name: 'Racer', car_id: 1, car_name: 'Camry', number: 3, team: '', mine: true,
  avatar_url: null, skin_id: null, skin_name: '',
}

describe('EntryCarPicker', () => {
  it('shows only the cars of the class and saves the new car', async () => {
    const calls = mockApi({
      'GET /api/catalog/cars': () => json(200, [car(1, 'Camry'), car(2, 'Mustang'), car(3, 'Audi GT3')]),
      'PUT /api/entries/7/car': () => json(200, { ...entry, car_id: 2, car_name: 'Mustang' }),
    })
    const changed = vi.fn()
    renderPage(<EntryCarPicker entry={entry as never} carIds={[1, 2]} onChanged={changed} />, {
      path: '/',
      url: '/',
      me: DRIVER,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar auto' }))
    const dialog = await screen.findByRole('dialog', { name: 'Elegí tu auto' })
    expect(await within(dialog).findByText('Mustang')).toBeInTheDocument()
    expect(within(dialog).queryByText('Audi GT3')).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByText('Mustang'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() => expect(changed).toHaveBeenCalled())
    expect(calls.find((c) => c.key === 'PUT /api/entries/7/car')!.body).toEqual({ car_id: 2 })
  })
})
