import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { TitleSection } from './TitleSection'

afterEach(() => vi.restoreAllMocks())

const driver = (entry_id: number, driver_name: string, points: number, status: string, own_destiny = false) => ({
  entry_id, driver_name, points, best_case: points + 54, status, own_destiny,
})

const title = (extra = {}) => ({
  planned_rounds: 8, rounds_with_result: 6, remaining_rounds: 2, max_per_round: 27, max_if_not_winner: 20,
  leader_id: 1, leader_target: 45, limits: ['provisional_results'],
  drivers: [driver(1, 'Ana', 150, 'contender', true), driver(2, 'Beto', 140, 'contender'), driver(3, 'Ceci', 50, 'eliminated')],
  ...extra,
})

const page = { path: '/seasons/:seasonId', url: '/seasons/4' }

describe('TitleSection', () => {
  it('shows the sure target, each contender, and the assumptions', async () => {
    mockApi({ 'GET /api/seasons/4/title': () => json(200, title()) })
    renderPage(<TitleSection seasonId={4} />, page)
    expect(await screen.findByText(/Ana es campeón seguro si suma 45 puntos en las 2 fechas/)).toBeInTheDocument()
    expect(screen.getByText(/Beto: máximo posible 194 pts · necesita que otros pierdan puntos/)).toBeInTheDocument()
    expect(screen.getByText('Ya no pueden ganar el título: Ceci.')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Supuestos del cálculo'))
    expect(screen.getByText(/Algunos resultados son provisionales/)).toBeVisible()
  })

  it('says when the leader depends on rivals or is already champion', async () => {
    mockApi({ 'GET /api/seasons/4/title': () => json(200, title({ leader_target: null })) })
    renderPage(<TitleSection seasonId={4} />, page)
    expect(await screen.findByText(/depende de los resultados de los rivales/)).toBeInTheDocument()
  })

  it('shows the champion', async () => {
    mockApi({
      'GET /api/seasons/4/title': () =>
        json(200, title({ leader_target: null, drivers: [driver(1, 'Ana', 150, 'champion'), driver(2, 'Beto', 50, 'eliminated')] })),
    })
    renderPage(<TitleSection seasonId={4} />, page)
    expect(await screen.findByText('¡Ana es campeón! Ningún rival puede alcanzarlo.')).toBeInTheDocument()
  })
})
