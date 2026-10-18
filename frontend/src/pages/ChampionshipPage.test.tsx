import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { ChampionshipPage } from './ChampionshipPage'

afterEach(() => vi.restoreAllMocks())

const progress = {
  season_id: 5,
  name: '2026',
  done: 3,
  total: 8,
  leader: 'Bing',
  next_round: { round_id: 9, number: 4, track_name: 'Monza', layout_name: 'GP', scheduled_at: '2026-10-20T00:00:00Z' },
}

function championship(canManage: boolean) {
  return {
    id: 1,
    name: 'LMDh',
    league_id: 1,
    league_name: 'Piston Cup',
    can_manage: canManage,
    provisional_reports: false,
    seasons: [{ id: 5, name: '2026', planned_round_count: 8, protest_window_minutes: 60, allow_repeat_layouts: false, voted_slots: 0 }],
    latest: progress,
    progress: [progress],
  }
}

const admin = {
  'GET /api/championships/1/members': () =>
    json(200, [{ user_id: 3, username: 'Ana Pérez', role: 'driver', custom_role_id: null, custom_role_name: null }]),
  'GET /api/championships/1/roles': () =>
    json(200, [{ id: 7, name: 'Cronista', capabilities: ['reports'], members: 0 }]),
  'GET /api/users': () => json(200, [{ id: 3, username: 'Ana Pérez' }]),
}

const page = { path: '/championships/:championshipId', url: '/championships/1' }

describe('ChampionshipPage', () => {
  it('shows a driver the season progress, the leader, and the next round', async () => {
    mockApi({ 'GET /api/championships/1': () => json(200, championship(false)) })
    renderPage(<ChampionshipPage />, { ...page, me: DRIVER })
    const bar = await screen.findByRole('progressbar', { name: '3 de 8 fechas' })
    expect(bar).toHaveAttribute('aria-valuenow', '3')
    const card = bar.closest('li')!
    expect(within(card).getByText('Bing')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Fecha 4 · Monza' })).toHaveAttribute('href', '/rounds/9')
    expect(screen.queryByText(/Protestas: 60 minutos/)).not.toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('changes the role of a member from the table', async () => {
    const calls = mockApi({
      'GET /api/championships/1': () => json(200, championship(true)),
      ...admin,
      'PUT /api/championships/1/members': () => json(200, {}),
    })
    renderPage(<ChampionshipPage />, page)
    await userEvent.click(await screen.findByRole('tab', { name: 'Miembros' }))
    await userEvent.selectOptions(await screen.findByLabelText('Rol de Ana Pérez'), 'custom:7')
    expect(calls.find((c) => c.key === 'PUT /api/championships/1/members')!.body).toEqual({
      user_id: 3,
      role: 'custom',
      custom_role_id: 7,
    })
  })

  it('turns a permission on from the roles table', async () => {
    const calls = mockApi({
      'GET /api/championships/1': () => json(200, championship(true)),
      ...admin,
      'PUT /api/roles/7': () => json(200, {}),
    })
    renderPage(<ChampionshipPage />, page)
    await userEvent.click(await screen.findByRole('tab', { name: 'Roles' }))
    await userEvent.click(await screen.findByLabelText('Sanciones para Cronista'))
    expect(calls.find((c) => c.key === 'PUT /api/roles/7')!.body).toEqual({
      name: 'Cronista',
      capabilities: ['reports', 'penalties'],
    })
  })
})
