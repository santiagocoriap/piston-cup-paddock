import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, carOf, json, mockApi, renderPage } from '../test-utils'
import { JoinRequestsPanel, JoinSeasonButton } from './JoinSeason'

afterEach(() => vi.restoreAllMocks())

const cars = [carOf({ id: 1, key: 'acura', name: 'Acura' }), carOf({ id: 2, key: 'cadillac', name: 'Cadillac' })]
const seasons = (free: boolean) => ({
  has_profile: true,
  seasons: [
    { season_id: 9, season_name: '2026', championship_id: 3, championship_name: 'LMDh', free_join: free, mine: null },
    { season_id: 8, season_name: '2025', championship_id: 3, championship_name: 'LMDh', free_join: false, mine: 'entered' },
  ],
})

async function fill(request: boolean) {
  await userEvent.click(screen.getByRole('button', { name: 'Unirme a una temporada' }))
  const dialog = await screen.findByRole('dialog', { name: 'Unirme a una temporada' })
  await userEvent.selectOptions(await within(dialog).findByRole('combobox', { name: 'Temporada' }), '9')
  await userEvent.click(within(dialog).getByRole('combobox', { name: 'Auto' }))
  await userEvent.click(await within(dialog).findByRole('option', { name: 'Cadillac' }))
  await userEvent.type(within(dialog).getByLabelText('Número'), '7')
  if (request) await userEvent.type(within(dialog).getByLabelText('Nota para el admin (opcional)'), 'Hola')
  return dialog
}

describe('JoinSeasonButton', () => {
  it('joins at once when the season has free join, and hides the seasons already entered', async () => {
    const calls = mockApi({
      'GET /api/join/seasons': () => json(200, seasons(true)),
      'GET /api/catalog/cars': () => json(200, cars),
      'POST /api/seasons/9/join': () => json(201, { status: 'joined', entry_id: 4 }),
    })
    const done = vi.fn()
    renderPage(<JoinSeasonButton onDone={done} />, { path: '/', url: '/' })
    const dialog = await fill(false)
    expect(within(dialog).queryByRole('option', { name: /2025/ })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Unirme' }))
    await vi.waitFor(() => expect(done).toHaveBeenCalledWith('joined', '2026'))
    expect(calls.find((c) => c.key === 'POST /api/seasons/9/join')!.body).toMatchObject({ car_id: 2, number: 7 })
  })

  it('sends a request, with a note, when the season has no free join', async () => {
    const calls = mockApi({
      'GET /api/join/seasons': () => json(200, seasons(false)),
      'GET /api/catalog/cars': () => json(200, cars),
      'POST /api/seasons/9/join': () => json(201, { status: 'requested', request_id: 1 }),
    })
    const done = vi.fn()
    renderPage(<JoinSeasonButton onDone={done} />, { path: '/', url: '/' })
    const dialog = await fill(true)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Pedir unirme' }))
    await vi.waitFor(() => expect(done).toHaveBeenCalledWith('requested', '2026'))
    expect(calls.find((c) => c.key === 'POST /api/seasons/9/join')!.body).toMatchObject({ note: 'Hola' })
  })
})

describe('JoinRequestsPanel', () => {
  const pending = [{ id: 5, driver_name: 'Newbie', car_id: 2, car_name: 'Cadillac', number: 7, team: '', note: 'Hola', created_at: '2026-10-17T10:00:00Z' }]

  it('approves a request, with the number the admin chose', async () => {
    const calls = mockApi({
      'GET /api/seasons/9/join-requests': () => json(200, pending),
      'POST /api/join-requests/5/approve': () => json(200, { status: 'joined', entry_id: 1 }),
    })
    const changed = vi.fn()
    renderPage(<JoinRequestsPanel seasonId={9} onChange={changed} />, { path: '/', url: '/', me: ADMIN })
    expect(await screen.findByText('Newbie')).toBeInTheDocument()
    const number = screen.getByRole('spinbutton', { name: 'Número' })
    await userEvent.clear(number)
    await userEvent.type(number, '8')
    await userEvent.click(screen.getByRole('button', { name: 'Aprobar' }))
    await vi.waitFor(() => expect(changed).toHaveBeenCalled())
    expect(calls.find((c) => c.key === 'POST /api/join-requests/5/approve')!.body).toEqual({ number: 8 })
  })

  it('declines a request, and shows nothing when none wait', async () => {
    const calls = mockApi({
      'GET /api/seasons/9/join-requests': () => json(200, pending),
      'POST /api/join-requests/5/decline': () => json(200, { status: 'declined' }),
    })
    renderPage(<JoinRequestsPanel seasonId={9} onChange={() => undefined} />, { path: '/', url: '/', me: ADMIN })
    await userEvent.click(await screen.findByRole('button', { name: 'Rechazar' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'POST /api/join-requests/5/decline')).toBe(true))
  })
})
