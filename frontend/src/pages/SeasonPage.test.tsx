import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { SeasonPage } from './SeasonPage'

afterEach(() => vi.restoreAllMocks())

function season(canManage: boolean) {
  return {
    id: 5,
    name: '2026',
    planned_round_count: 8,
    championship_id: 1,
    championship_name: 'LMDh',
    can_manage: canManage,
    entries: [
      { id: 1, driver_id: 3, driver_name: 'Bing', car_id: 2, car_name: 'Acura', number: 93, team: 'MSR' },
    ],
    rounds: [
      {
        id: 9,
        number: 1,
        track_layout_id: 4,
        track_name: 'Highlands',
        layout_name: 'Long',
        scheduled_at: '2026-10-19T00:30:00Z',
        origin: 'manual',
      },
    ],
  }
}

const catalog = {
  'GET /api/catalog/tracks': () =>
    json(200, [{ id: 7, key: 'ks_highlands', name: 'Highlands', layouts: [{ id: 4, key: 'layout_long', name: 'Long' }] }]),
  'GET /api/catalog/cars': () => json(200, [{ id: 2, key: 'acura', name: 'Acura' }]),
  'GET /api/drivers': () => json(200, []),
}

const show = (me = undefined as typeof DRIVER | undefined) =>
  renderPage(<SeasonPage />, { path: '/seasons/:seasonId', url: '/seasons/5', me })

describe('SeasonPage', () => {
  it('shows the calendar with the manual origin and the entries', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)) })
    show(DRIVER)
    const calendar = (await screen.findAllByRole('table'))[0]
    expect(within(calendar).getByText('Highlands · Long')).toBeInTheDocument()
    expect(within(calendar).getByText('Manual')).toBeInTheDocument()
    expect(screen.getByText('MSR')).toBeInTheDocument()
  })

  it('hides the forms from a driver', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)) })
    show(DRIVER)
    await screen.findAllByRole('table')
    expect(screen.queryByRole('form', { name: 'Agregar fecha' })).not.toBeInTheDocument()
  })

  it('sends a new round with the timezone of the browser', async () => {
    const calls = mockApi({
      'GET /api/seasons/5': () => json(200, season(true)),
      'POST /api/seasons/5/rounds': () => json(201, season(true).rounds[0]),
      ...catalog,
    })
    show()
    const form = await screen.findByRole('form', { name: 'Agregar fecha' })
    await userEvent.selectOptions(await within(form).findByLabelText('Pista y trazado'), '4')
    await userEvent.type(within(form).getByLabelText('Día y hora'), '2026-10-18T21:30')
    await userEvent.click(within(form).getByRole('button', { name: 'Agregar' }))
    const body = calls.find((call) => call.key === 'POST /api/seasons/5/rounds')!.body as {
      track_layout_id: number
      scheduled_at: string
    }
    expect(body.track_layout_id).toBe(4)
    expect(body.scheduled_at).toMatch(
      /^2026-10-18T21:30:00[+-]\d{2}:\d{2}$/,
    )
  })

  it('shows the API error when a number is taken', async () => {
    mockApi({
      'GET /api/seasons/5': () => json(200, season(true)),
      'POST /api/seasons/5/entries': () => json(409, { detail: 'entry_exists' }),
      ...catalog,
      'GET /api/drivers': () => json(200, [{ id: 3, display_name: 'Bing', steam_guid: null, user_id: null, username: null }]),
    })
    show()
    const form = await screen.findByRole('form', { name: 'Inscribir piloto' })
    await userEvent.selectOptions(await within(form).findByLabelText('Piloto'), '3')
    await userEvent.selectOptions(await within(form).findByLabelText('Auto'), '2')
    await userEvent.type(within(form).getByLabelText('Número'), '93')
    await userEvent.click(within(form).getByRole('button', { name: 'Agregar' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'Ese piloto o ese número ya está inscripto en la temporada.',
    )
  })
})
