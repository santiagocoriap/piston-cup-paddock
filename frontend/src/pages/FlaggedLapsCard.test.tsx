import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { FlaggedLapsCard } from './FlaggedLapsCard'

afterEach(() => vi.restoreAllMocks())

const lap = (id: number, extra = {}) => ({
  id, steam_guid: '76561190000000055', driver_id: 5, driver_name: 'Vice', track: 'ks_laguna_seca',
  car: 'ks_mazda_mx5_cup', lap_number: 3, lap_time_ms: 101_716, recorded_at: '2026-11-02T00:10:00Z',
  issues: ['no_server_lap'], round_id: 11, round_number: 1, ...extra,
})

describe('FlaggedLapsCard', () => {
  it('shows nothing when no lap has issues', async () => {
    mockApi({ 'GET /api/championships/1/telemetry/flagged': () => json(200, []) })
    renderPage(<FlaggedLapsCard championshipId={1} />, { path: '/', url: '/' })
    await vi.waitFor(() => expect(screen.queryByText('Vueltas para revisar')).not.toBeInTheDocument())
  })

  it('counts a lap for its round with the session', async () => {
    const calls = mockApi({
      'GET /api/championships/1/telemetry/flagged': () => json(200, [lap(7)]),
      'POST /api/telemetry-laps/7/accept': () => json(200, { state: 'league', issues: [] }),
    })
    renderPage(<FlaggedLapsCard championshipId={1} />, { path: '/', url: '/' })
    expect(await screen.findByText('El servidor no tiene esta vuelta')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Sesión de la vuelta'), 'qualifying')
    await userEvent.click(screen.getByRole('button', { name: 'Contar' }))
    await vi.waitFor(() =>
      expect(calls.find((c) => c.key === 'POST /api/telemetry-laps/7/accept')!.body).toEqual({ round_id: 11, session_type: 'qualifying' }),
    )
  })

  it('says why a lap still does not count after a new check', async () => {
    mockApi({
      'GET /api/championships/1/telemetry/flagged': () => json(200, [lap(8, { driver_id: null, driver_name: null, issues: ['unknown_driver'] })]),
      'POST /api/telemetry-laps/8/recheck': () => json(200, { state: 'rejected', issues: ['unknown_driver'] }),
    })
    renderPage(<FlaggedLapsCard championshipId={1} />, { path: '/', url: '/' })
    expect(await screen.findByText('76561190000000055')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Contar' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Controlar de nuevo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('La vuelta sigue sin contar')
  })
})
