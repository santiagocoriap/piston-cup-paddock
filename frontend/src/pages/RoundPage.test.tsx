import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { RoundPage } from './RoundPage'

afterEach(() => vi.restoreAllMocks())

function round(canManage: boolean, result: unknown = null) {
  return {
    id: 9,
    number: 1,
    season_id: 5,
    season_name: '2026',
    championship_name: 'LMDh',
    track_name: 'Highlands',
    layout_name: 'Long',
    scheduled_at: '2026-10-19T00:30:00Z',
    can_manage: canManage,
    rules: { version: 1, points_by_position: [25, 18, 15], pole_bonus: 0, fastest_lap_bonus: 0 },
    entries: [
      { entry_id: 1, number: 93, driver_name: 'Bing', car_name: 'Acura' },
      { entry_id: 2, number: 7, driver_name: 'Vice', car_name: 'Vanwall' },
      { entry_id: 3, number: 3, driver_name: 'Billy', car_name: 'Cadillac' },
    ],
    result,
  }
}

const show = (me = undefined as typeof DRIVER | undefined) =>
  renderPage(<RoundPage />, { path: '/rounds/:roundId', url: '/rounds/9', me })

describe('RoundPage', () => {
  it('shows the result with points and the DNF mark', async () => {
    mockApi({
      'GET /api/rounds/9': () =>
        json(200, round(false, [
          { entry_id: 1, status: 'finished', position: 1, pole: false, fastest_lap: false, number: 93, driver_name: 'Bing', points: 25 },
          { entry_id: 2, status: 'dnf', position: 2, pole: false, fastest_lap: false, number: 7, driver_name: 'Vice', points: 18 },
          { entry_id: 3, status: 'dns', position: null, pole: false, fastest_lap: false, number: 3, driver_name: 'Billy', points: 0 },
        ])),
    })
    show(DRIVER)
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('row', { name: /Vice/ })).toHaveTextContent('DNF')
    expect(within(table).getByRole('row', { name: /Billy/ })).toHaveTextContent('DNS')
    expect(screen.queryByRole('button', { name: 'Guardar resultado' })).not.toBeInTheDocument()
  })

  it('sends only the drivers who took part, with their positions', async () => {
    const calls = mockApi({
      'GET /api/rounds/9': () => json(200, round(true)),
      'PUT /api/rounds/9/result': () => json(200, round(true, [])),
    })
    show()
    await userEvent.selectOptions(await screen.findByLabelText('Estado Bing'), 'finished')
    await userEvent.type(screen.getByLabelText('Pos. Bing'), '1')
    await userEvent.selectOptions(screen.getByLabelText('Estado Vice'), 'dnf')
    await userEvent.type(screen.getByLabelText('Pos. Vice'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar resultado' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Resultado guardado.')
    const put = calls.find((call) => call.key === 'PUT /api/rounds/9/result')!
    expect(put.body).toEqual({
      lines: [
        { entry_id: 1, status: 'finished', position: 1, pole: false, fastest_lap: false },
        { entry_id: 2, status: 'dnf', position: 2, pole: false, fastest_lap: false },
      ],
    })
  })

  it('shows the rule that a result breaks', async () => {
    mockApi({
      'GET /api/rounds/9': () => json(200, round(true)),
      'PUT /api/rounds/9/result': () => json(422, { detail: 'positions_not_continuous' }),
    })
    show()
    await userEvent.selectOptions(await screen.findByLabelText('Estado Bing'), 'finished')
    await userEvent.type(screen.getByLabelText('Pos. Bing'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar resultado' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('sin huecos ni repetidas')
  })

  it('disables the position for DNS and DSQ', async () => {
    mockApi({ 'GET /api/rounds/9': () => json(200, round(true)) })
    show()
    await userEvent.selectOptions(await screen.findByLabelText('Estado Bing'), 'dsq')
    expect(screen.getByLabelText('Pos. Bing')).toBeDisabled()
  })
})
