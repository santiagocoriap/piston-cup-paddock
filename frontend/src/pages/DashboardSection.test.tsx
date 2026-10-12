import { screen, within } from '@testing-library/react'
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
    ballast_kg: 7, restrictor_pct: 1,
  },
}

describe('DashboardSection', () => {
  it('shows position, points, recent results, and the next round with handicaps', async () => {
    mockApi({ 'GET /api/dashboard': () => json(200, { has_driver_profile: true, seasons: [card] }) })
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    const article = await screen.findByRole('article', { name: 'LMDh · 2026' })
    expect(within(article).getByText('P2')).toBeInTheDocument()
    expect(within(article).getByText('7 pts del líder')).toBeInTheDocument()
    expect(within(article).getByText(/P4 DNF · 12 pts/)).toBeInTheDocument()
    expect(within(article).getByText('R3 · Imola · GP')).toBeInTheDocument()
    expect(within(article).getByText('7 kg · 1 %')).toBeInTheDocument()
    expect(within(article).getByText('Fecha a confirmar')).toBeInTheDocument()
    expect(within(article).getByRole('link', { name: 'Ver briefing' })).toHaveAttribute('href', '/rounds/3')
  })

  it('tells a user without a driver profile what to do', async () => {
    mockApi({ 'GET /api/dashboard': () => json(200, { has_driver_profile: false, seasons: [] }) })
    renderPage(<DashboardSection />, { path: '/', url: '/', me: DRIVER })
    expect(await screen.findByText(/no tiene un piloto vinculado/)).toBeInTheDocument()
  })
})
