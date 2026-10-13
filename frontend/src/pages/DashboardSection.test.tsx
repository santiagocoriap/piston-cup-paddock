import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { DashboardSection } from './DashboardSection'

afterEach(() => vi.restoreAllMocks())

const card = {
  season_id: 5, season_name: '2026', championship_name: 'LMDh', entry_number: 7, car_name: 'Acura',
  rank: 2, entries: 10, points: 43, wins: 1, leader_points: 50,
  new_reports: [{ round_id: 3, round_number: 1, track_name: 'Spa' }],
  recent: [
    { round_id: 2, round_number: 2, track_name: 'Monza', status: 'dnf', position: 4, points: 12 },
    { round_id: 1, round_number: 1, track_name: 'Spa', status: 'finished', position: 1, points: 25 },
  ],
  next_round: {
    round_id: 3, round_number: 3, track_name: 'Imola', layout_name: 'GP', scheduled_at: null,
    event_timezone: 'America/Argentina/Buenos_Aires',
    ballast_kg: 7, restrictor_pct: 1, my_attendance: null, attending: 4,
    previous_ballast_kg: 10, previous_restrictor_pct: 1,
    conditions: { time_of_day: '15:30', weather: 'Despejado', air_temp_c: 24, track_temp_c: 31, grip: '' },
  },
}

const ballots = [
  { id: 8, kind: 'track', title: 'Pista de la R4', status: 'open', parent_id: null, winners: [], closes_at: null, voted: false },
  { id: 9, kind: 'track', title: 'Desempate R4', status: 'open', parent_id: 8, winners: [], closes_at: null, voted: false },
  { id: 11, kind: 'car', title: 'Auto GT', status: 'open', parent_id: null, winners: [], closes_at: '2026-10-18T23:59:00Z', voted: true },
  { id: 10, kind: 'car', title: 'Auto 2027', status: 'closed', parent_id: null, winners: [], closes_at: null, voted: null },
]

function mockHome(extra: Record<string, () => Response> = {}) {
  return mockApi({
    'GET /api/dashboard': () => json(200, { has_driver_profile: true, seasons: [card] }),
    'GET /api/seasons/5/ballots': () => json(200, ballots),
    ...extra,
  })
}

describe('DashboardSection', () => {
  it('shows the next race, the position, the handicap and the last results', async () => {
    mockHome()
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    expect(await screen.findByRole('heading', { name: 'Hola, racer' })).toBeInTheDocument()
    const article = await screen.findByRole('article', { name: 'LMDh · 2026' })
    expect(within(article).getByRole('heading', { name: 'Imola' })).toBeInTheDocument()
    expect(within(article).getByText('Fecha a confirmar')).toBeInTheDocument()
    expect(within(article).getByText('7 kg · 1 %')).toBeInTheDocument()
    expect(within(article).getByText('7 pts del líder', { exact: false })).toBeInTheDocument()
    expect(within(article).getByText(/P4 DNF · 12 pts/)).toBeInTheDocument()
    expect(within(article).getByRole('img', { name: '7 kg de un máximo de 45 kg' })).toBeInTheDocument()
    expect(within(article).getByRole('link', { name: 'Ver briefing' })).toHaveAttribute('href', '/rounds/3')
  })

  it('lists what to do: attendance, open ballots with the runoff, and new reports', async () => {
    mockHome()
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    const todo = (await screen.findByRole('heading', { name: 'Qué tenés que hacer' })).parentElement!
    expect(within(todo).getByText('Confirmá si vas a Imola')).toBeInTheDocument()
    expect(await within(todo).findByText('Votá: Pista de la R4')).toBeInTheDocument()
    expect(within(todo).getByText('Segunda vuelta: Desempate R4')).toBeInTheDocument()
    expect(within(todo).queryByText(/Auto 2027/)).not.toBeInTheDocument()
    expect(within(todo).getByText('Reporte nuevo: R1 · Spa')).toBeInTheDocument()
    expect(within(todo).getByText('Ya votaste: Auto GT')).toBeInTheDocument()
    expect(within(todo).getByText(/^Cierra /)).toBeInTheDocument()
    expect(within(todo).getAllByRole('listitem').at(-1)).toHaveTextContent('Ya votaste: Auto GT')
  })

  it('shows the announced conditions and how the handicap changed', async () => {
    mockHome()
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    const article = await screen.findByRole('article', { name: 'LMDh · 2026' })
    expect(within(article).getByText('Despejado')).toBeInTheDocument()
    expect(within(article).getByText(/aire 24 °C · pista 31 °C/)).toBeInTheDocument()
    expect(within(article).getByText('15:30')).toBeInTheDocument()
    expect(within(article).getByText('Antes 10 kg · −3 kg')).toBeInTheDocument()
    expect(within(article).getByText('Igual que antes (1 %)')).toBeInTheDocument()
  })

  it('says the conditions are not confirmed when none are announced', async () => {
    mockApi({
      'GET /api/dashboard': () =>
        json(200, { has_driver_profile: true, seasons: [{ ...card, next_round: { ...card.next_round, conditions: null } }] }),
      'GET /api/seasons/5/ballots': () => json(200, []),
    })
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    expect(await screen.findByText('A confirmar')).toBeInTheDocument()
  })

  it('saves the attendance answer from the next-race panel', async () => {
    const calls = mockHome({
      'PUT /api/rounds/3/attendance': () =>
        json(200, { can_answer: true, mine: 'yes', yes: 5, maybe: 0, no: 0, rows: [] }),
    })
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    await userEvent.click(await screen.findByRole('button', { name: /Sí, voy/ }))
    expect(calls.find((c) => c.key === 'PUT /api/rounds/3/attendance')!.body).toEqual({ answer: 'yes' })
    expect(await screen.findByText('Tu respuesta: Sí')).toBeInTheDocument()
    expect(screen.getByText('5 pilotos confirmados')).toBeInTheDocument()
    expect(screen.queryByText('Confirmá si vas a Imola')).not.toBeInTheDocument()
  })

  it('tells a user without a driver profile what to do', async () => {
    mockApi({ 'GET /api/dashboard': () => json(200, { has_driver_profile: false, seasons: [] }) })
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    expect(await screen.findByText(/no tiene un piloto vinculado/)).toBeInTheDocument()
  })
})
