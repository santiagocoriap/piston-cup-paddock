import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { DriverProfilePage } from './DriverProfilePage'

afterEach(() => vi.restoreAllMocks())

const result = (round: number, position: number, points: number) => ({
  round_id: 8 + round, round_number: round, track_name: 'Highlands', status: 'finished', position, points,
})

const badge = (key: string, count: number, goal = 1) => ({ key, count, goal, achieved: count >= goal })

const profile = (extra = {}) => ({
  id: 7, display_name: 'Driver 01', can_adjust: true,
  career: { raw_points: 125, points: 125, level: 2, next_level_points: 200, adjustments: [] },
  seasons: [
    {
      season_id: 4, season_name: '2026', championship_name: 'LMDh', rank: 1, entries: 5, points: 125, wins: 5,
      podiums: 5, starts: 5, number: 93, car_name: 'Acura ARX-06', team: 'MSR',
      history: [result(1, 2, 18), result(2, 1, 25)],
    },
  ],
  safety: [{ championship_name: 'LMDh', rating: 3.4, status: 'provisional', laps: 40, points: 2 }],
  records: [{ track: 'Highlands · Long', car: 'Acura', category: 'race', lap_time_ms: 189296, round_id: 9 }],
  restarts_caused: [{ round_id: 9, label: '2026 R1', attempt: 3, reason: 'first_lap_crash', shared: false }],
  achievements: [badge('win', 5), badge('podium', 5), badge('pole', 0), badge('starts', 5, 10)],
  stats: {
    starts: 5, wins: 5, podiums: 5, top5: 5, poles: 2, fastest_laps: 3, best_finish: 1, average_finish: 1.4,
    points: 125, laps: 1240, records: 1, win_rate: 100, dnfs: 1, dsqs: 0, penalties: 2, incident_points: 6,
    restarts_caused: 1,
  },
  ...extra,
})

const page = { path: '/drivers/:driverId', url: '/drivers/7' }

describe('DriverProfilePage', () => {
  it('shows the hero, the level ring, badges, results, seasons, safety, records, and restarts', async () => {
    mockApi({ 'GET /api/drivers/7/profile': () => json(200, profile({ can_adjust: false })) })
    renderPage(<DriverProfilePage />, { ...page, me: DRIVER })
    expect(await screen.findByRole('heading', { name: 'Driver 01' })).toBeInTheDocument()
    expect(screen.getByText('Acura ARX-06 · MSR')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Nivel 2: 125 de 200 puntos de carrera' })).toBeInTheDocument()
    const stats = screen.getByRole('region', { name: 'Estadísticas' })
    const value = (label: string) => within(stats).getByText(label).nextElementSibling?.textContent
    expect([value('Poles'), value('Mejor puesto'), value('Puesto promedio'), value('Vueltas')]).toEqual(['2', 'P1', 'P1,4', '1240'])
    expect([value('Abandonos'), value('Sanciones'), value('Reinicios causados'), value('Victorias por largada')]).toEqual(['1', '2', '1', '100 %'])
    expect(screen.getByText('Solo cuentan los resultados oficiales.')).toBeInTheDocument()

    const badges = screen.getByRole('region', { name: 'Logros' })
    expect(within(badges).getByText('Primera victoria').closest('li')).toHaveClass('achieved')
    expect(within(badges).getByText('Primera pole').closest('li')).toHaveClass('locked')
    expect(within(badges).getByText('5 de 10')).toBeInTheDocument()

    expect(screen.getByRole('img', { name: /Posición por fecha: Fecha 1 P2, Fecha 2 P1/ })).toBeInTheDocument()
    expect(screen.getByText('P1 de 5 · 125 pts')).toBeInTheDocument()
    expect(screen.getByText(/25.0 pts por largada/)).toBeInTheDocument()
    expect(screen.getByText('3.40')).toBeInTheDocument()
    expect(screen.getByText('3:09.296')).toBeInTheDocument()
    expect(screen.getByText(/Choque en la primera vuelta/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ajustar puntos de carrera' })).not.toBeInTheDocument()
  })

  it('hides the records and the restarts when there are none', async () => {
    mockApi({ 'GET /api/drivers/7/profile': () => json(200, profile({ records: [], restarts_caused: [] })) })
    renderPage(<DriverProfilePage />, { ...page, me: DRIVER })
    await screen.findByRole('heading', { name: 'Driver 01' })
    expect(screen.queryByRole('heading', { name: 'Récords' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Reinicios causados/ })).not.toBeInTheDocument()
  })

  it('lets an admin adjust the career in a dialog', async () => {
    const calls = mockApi({
      'GET /api/drivers/7/profile': () => json(200, profile()),
      'POST /api/drivers/7/career': () =>
        json(200, profile({ career: { raw_points: 125, points: 0, level: 1, next_level_points: 100, adjustments: [
          { kind: 'reset', points: 0, reason: 'Nueva liga', created_by: 'santi', created_at: '2026-10-12T10:00:00Z' },
        ] } })),
    })
    renderPage(<DriverProfilePage />, page)
    await userEvent.click(await screen.findByRole('button', { name: 'Ajustar puntos de carrera' }))
    const form = await screen.findByRole('form', { name: 'Ajustar puntos de carrera' })
    await userEvent.selectOptions(within(form).getByLabelText('Tipo'), 'reset')
    await userEvent.type(within(form).getByLabelText('Motivo'), 'Nueva liga')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText(/125 puntos oficiales en total/)).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/drivers/7/career')!.body).toEqual({ kind: 'reset', points: 0, reason: 'Nueva liga' })
    // The history of the changes is in the same dialog.
    await userEvent.click(screen.getByRole('button', { name: 'Ajustar puntos de carrera' }))
    expect(await screen.findByText(/Volver a cero · Nueva liga · santi/)).toBeInTheDocument()
  })
})
