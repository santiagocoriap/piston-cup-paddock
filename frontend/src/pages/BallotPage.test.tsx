import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, DRIVER, json, mockApi, renderPage } from '../test-utils'
import { BallotPage } from './BallotPage'

afterEach(() => vi.restoreAllMocks())

function ballot(extra: Record<string, unknown> = {}) {
  return {
    id: 7, season_id: 5, season_name: '2026', championship_name: 'LMDh', kind: 'track', title: 'Pistas 2026',
    status: 'open', method: 'multiple', selection_limit: 2, slots: 6, choice_visibility: 'hidden',
    totals_visibility: 'live', allow_vote_changes: true, closes_at: null, eligible_roles: ['driver', 'admin'],
    prior_season_id: null, min_prior_starts: 0, max_runoffs: null, power_exceptions: [{ username: 'santi', power: 2, voted: false }],
    power_overrides: { 1: 2 }, closed_early: false, close_reason: '', class_rounds: false, stage: 'main', parent: null, runoffs: [], subclass_rounds: [], can_manage: false,
    can_vote: true, my_power: 1, my_choices: [], voted_count: 1, voter_count: 5, totals_visible: true,
    choices_visible: false, tie: null, voters: null,
    options: [
      { id: 1, label: 'Spa - GP', track_layout_id: 1, selected: false, selected_by: '', votes: 3, voters: null },
      { id: 2, label: 'Monza - GP', track_layout_id: 2, selected: false, selected_by: '', votes: 1, voters: null },
      { id: 3, label: 'Imola - GP', track_layout_id: 3, selected: false, selected_by: '', votes: 0, voters: null },
    ],
    ...extra,
  }
}

const show = (me = DRIVER as typeof DRIVER | undefined) =>
  renderPage(<BallotPage />, { path: '/ballots/:ballotId', url: '/ballots/7', me })

describe('BallotPage', () => {
  it('shows the cars of a class option: pictures and the number of cars', async () => {
    const tc = {
      id: 9, label: 'TC', track_layout_id: null, car_class_id: 4, selected: false, selected_by: '', votes: 0, voters: null,
      image_url: '/a.jpg', images: ['/a.jpg', '/b.jpg', '/c.jpg'], car_count: 12,
    }
    mockApi({
      'GET /api/ballots/7': () => json(200, ballot({ kind: 'car_class', options: [tc] })),
      'GET /api/ballots/7/options/9/cars': () =>
        json(200, [
          { subclass: null, cars: [{ id: 1, name: 'Torino', brand: 'IKA', year: 2025, image_url: null }] },
          { subclass: 'TC 2005', cars: [{ id: 2, name: 'Falcon', brand: 'Ford', year: 2005, image_url: '/f.jpg' }] },
        ]),
    })
    const { container } = show()
    const button = await screen.findByRole('button', { name: 'Ver los 12 autos' })
    expect(container.querySelectorAll('.vote-media.collage img')).toHaveLength(3)
    await userEvent.click(button)
    expect(await screen.findByText('Falcon')).toBeInTheDocument()
    expect(screen.getByText('Torino')).toBeInTheDocument()
    expect(screen.getByText('TC 2005')).toBeInTheDocument()
    expect(screen.getByText('Ford · 2005')).toBeInTheDocument()
    // The button opens the list: it does not choose the option.
    expect(container.querySelector('.vote-card input')).not.toBeChecked()
  })

  it('explains the method, the power, and the live totals before the vote', async () => {
    mockApi({ 'GET /api/ballots/7': () => json(200, ballot()) })
    show()
    expect(await screen.findByText('Las pistas votadas llenan 6 fechas libres.')).toBeInTheDocument()
    expect(screen.getByText('Votos con otro valor: santi ×2')).toBeInTheDocument()
    expect(screen.getByText('Tu voto vale 1.')).toBeInTheDocument()
    expect(screen.getByLabelText(/Spa - GP/)).toBeInTheDocument()
    expect(screen.getByText(/3 votos/)).toBeInTheDocument()
  })

  it('stops a third choice when the limit is two, and sends the vote', async () => {
    const calls = mockApi({
      'GET /api/ballots/7': () => json(200, ballot()),
      'PUT /api/ballots/7/vote': () => json(200, ballot({ my_choices: [1, 2] })),
    })
    show()
    await userEvent.click(await screen.findByLabelText(/Spa - GP/))
    await userEvent.click(screen.getByLabelText(/Monza - GP/))
    expect(screen.getByLabelText(/Imola - GP/)).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Votar' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Tu voto quedó guardado.')
    expect(calls.find((c) => c.key === 'PUT /api/ballots/7/vote')!.body).toEqual({ option_ids: [1, 2] })
  })

  it('shows the tie and the runoff button to an admin', async () => {
    mockApi({
      'GET /api/ballots/7': () =>
        json(200, ballot({
          status: 'closed', can_manage: true, can_vote: false, tie: { option_ids: [2, 3], open_slots: 1 },
          voters: [{ username: 'v1', power: 1, voted: true }],
        })),
      'GET /api/catalog/tracks': () => json(200, []),
      'GET /api/users': () => json(200, []),
    })
    show(ADMIN)
    expect(await screen.findByText('Empate: 2 opciones compiten por 1 lugares.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir desempate' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Elegir a mano' }))
    const decide = await screen.findByRole('form', { name: 'Elegir a mano' })
    expect(within(decide).getAllByRole('button', { name: /^Agregar (?!todos)/ })).toHaveLength(2)
  })

  it('shows the results as bars with the share, the winner, and the voters', async () => {
    mockApi({
      'GET /api/ballots/7': () =>
        json(200, ballot({
          status: 'decided', can_vote: false, my_choices: [1],
          options: [
            { id: 1, label: 'Spa - GP', track_layout_id: 1, selected: true, selected_by: 'vote', votes: 3, voters: ['v1'],
              image_url: '/spa.png', voter_pictures: [{ username: 'v1', avatar_url: null }] },
            { id: 2, label: 'Monza - GP', track_layout_id: 2, selected: false, selected_by: '', votes: 1, voters: [] },
          ],
        })),
    })
    show()
    const results = await screen.findByRole('region', { name: 'Resultados' })
    const bars = within(results).getAllByRole('listitem')
    expect(within(bars[0]).getByText('75 %')).toBeInTheDocument()
    expect(within(bars[0]).getByText('por votos')).toBeInTheDocument()
    expect(within(bars[0]).getByText('Tu elección')).toBeInTheDocument()
    expect(within(bars[0]).getByLabelText('v1')).toBeInTheDocument()
    expect(within(bars[1]).getByText('25 %')).toBeInTheDocument()
  })

  it('hides the vote form from a user who is not a voter', async () => {
    mockApi({ 'GET /api/ballots/7': () => json(200, ballot({ can_vote: false, my_power: 0 })) })
    show()
    expect(await screen.findByText('No estás en la lista de votantes.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Votar' })).not.toBeInTheDocument()
  })
})

describe('BallotPage extras', () => {
  it('shows the participation rule, the voters, and the reminder button', async () => {
    const data = ballot({
      can_manage: true, status: 'open', closes_at: '2026-10-20T22:00:00Z', remind_hours_before: 24,
      min_participation_pct: 75, low_participation_action: 'admin', voted_names: ['v1', 'v2'],
    })
    const calls = mockApi({
      'GET /api/ballots/7': () => json(200, data),
      'POST /api/ballots/7/remind': () => json(200, { ...data, reminded_at: '2026-10-19T22:00:00Z' }),
      'GET /api/catalog/tracks': () => json(200, []),
      'GET /api/users': () => json(200, []),
    })
    show(ADMIN)
    expect(await screen.findByText(/Tiene que votar al menos el 75 %/)).toBeInTheDocument()
    expect(screen.getByText('Ya votaron: v1, v2')).toBeInTheDocument()
    expect(screen.getByText(/Recordatorio 24 horas antes del cierre/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Administrar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Recordar ahora a quien no votó' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Enviar recordatorio' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'POST /api/ballots/7/remind')).toBe(true))
  })
})
