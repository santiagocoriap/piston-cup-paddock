import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { SafetySection } from './SafetySection'

afterEach(() => vi.restoreAllMocks())

describe('SafetySection', () => {
  it('shows ratings, statuses, and the explanation of each change', async () => {
    mockApi({
      'GET /api/seasons/4/safety': () =>
        json(200, {
          rules_version: 'safety-1', provisional_laps: 50, computed_at: '2026-10-12T10:00:00Z',
          drivers: [
            {
              entry_id: 1, driver_name: 'Ana', rating: 3.0, status: 'provisional', laps: 10, points: 2, per_100_laps: 20,
              history: [
                { round_id: 9, label: '2026 R1 Highlands', status: 'rated', laps: 10, points: 2, change: 0, rating_after: 3.0,
                  explanation: ['2 pts · lap 3 · car · 60 km/h · Ana + Beto'] },
                { round_id: 10, label: '2026 R2 Spa', status: 'unknown', laps: 12, points: 0, change: 0, rating_after: 3.0, explanation: [] },
              ],
            },
            { entry_id: 2, driver_name: 'Ceci', rating: 3.0, status: 'unknown', laps: 0, points: 0, per_100_laps: null, history: [] },
          ],
        }),
    })
    renderPage(<SafetySection seasonId={4} />, { path: '/seasons/:seasonId', url: '/seasons/4' })
    expect(await screen.findByText('provisional')).toBeInTheDocument()
    expect(screen.getByText('sin datos')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Cambios de Ana'))
    expect(screen.getByText(/10 vueltas \+0.10, 2 puntos -0.10 = 0.00 → 3.00/)).toBeInTheDocument()
    expect(screen.getByText('2 pts · lap 3 · car · 60 km/h · Ana + Beto')).toBeInTheDocument()
    expect(screen.getByText(/no cuenta como carrera limpia/)).toBeInTheDocument()
  })
})
