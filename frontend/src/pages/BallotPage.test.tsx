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
    power_overrides: { 1: 2 }, closed_early: false, close_reason: '', parent: null, runoffs: [], can_manage: false,
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
    const decide = screen.getByRole('form', { name: 'Elegir a mano' })
    expect(within(decide).getAllByRole('checkbox')).toHaveLength(2)
  })

  it('hides the vote form from a user who is not a voter', async () => {
    mockApi({ 'GET /api/ballots/7': () => json(200, ballot({ can_vote: false, my_power: 0 })) })
    show()
    expect(await screen.findByText('No estás en la lista de votantes.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Votar' })).not.toBeInTheDocument()
  })
})
