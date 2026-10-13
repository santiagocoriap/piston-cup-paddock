import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { DriverProfilePage } from './DriverProfilePage'

afterEach(() => vi.restoreAllMocks())

const profile = (extra = {}) => ({
  id: 7, display_name: 'Driver 01', can_adjust: true,
  career: { raw_points: 125, points: 125, level: 2, next_level_points: 200, adjustments: [] },
  seasons: [{ season_id: 4, season_name: '2026', championship_name: 'LMDh', rank: 1, entries: 5, points: 125, wins: 5, podiums: 5, starts: 5 }],
  safety: [{ championship_name: 'LMDh', rating: 3.4, status: 'provisional', laps: 40, points: 2 }],
  records: [{ track: 'Highlands · Long', car: 'Acura', category: 'race', lap_time_ms: 189296, round_id: 9 }],
  restarts_caused: [{ round_id: 9, label: '2026 R1', attempt: 3, reason: 'first_lap_crash', shared: false }],
  ...extra,
})

const page = { path: '/drivers/:driverId', url: '/drivers/7' }

describe('DriverProfilePage', () => {
  it('shows level, seasons, safety, records, and restarts', async () => {
    mockApi({ 'GET /api/drivers/7/profile': () => json(200, profile({ can_adjust: false })) })
    renderPage(<DriverProfilePage />, { ...page, me: DRIVER })
    expect(await screen.findByRole('heading', { name: 'Driver 01' })).toBeInTheDocument()
    expect(screen.getByText(/Próximo nivel con 200 puntos \(25 %\)/)).toBeInTheDocument()
    expect(screen.getByText('25.0')).toBeInTheDocument() // Points per start.
    expect(screen.getByText(/LMDh: 3.40/)).toBeInTheDocument()
    expect(screen.getByText('3:09.296')).toBeInTheDocument()
    expect(screen.getByText(/Choque en la primera vuelta/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Ajustar puntos de carrera' })).not.toBeInTheDocument()
  })

  it('lets an admin adjust the career with a reason', async () => {
    const calls = mockApi({
      'GET /api/drivers/7/profile': () => json(200, profile()),
      'POST /api/drivers/7/career': () =>
        json(200, profile({ career: { raw_points: 125, points: 0, level: 1, next_level_points: 100, adjustments: [
          { kind: 'reset', points: 0, reason: 'Nueva liga', created_by: 'santi', created_at: '2026-10-12T10:00:00Z' },
        ] } })),
    })
    renderPage(<DriverProfilePage />, page)
    await screen.findByRole('heading', { name: 'Driver 01' })
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'reset')
    await userEvent.type(screen.getByLabelText('Motivo'), 'Nueva liga')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText(/Volver a cero · Nueva liga · santi/)).toBeInTheDocument()
    expect(screen.getByText(/125 puntos oficiales en total/)).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/drivers/7/career')!.body).toEqual({ kind: 'reset', points: 0, reason: 'Nueva liga' })
  })
})
