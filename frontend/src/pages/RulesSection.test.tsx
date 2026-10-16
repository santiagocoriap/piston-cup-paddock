import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { RulesSection } from './RulesSection'

afterEach(() => vi.restoreAllMocks())

const version = {
  number: 1, points_by_position: [25, 18, 15], pole_bonus: 0, fastest_lap_bonus: 0, ballast_steps: [10, 10, 5, 3],
  restrictor_steps: [2, 2, 1], ballast_cap: 45, restrictor_cap: 5, ballast_reduction: 3, restrictor_reduction: 1,
  reason: '', recalculated: false, created_at: '2026-10-01T10:00:00Z', created_by: null,
}

describe('RulesSection', () => {
  it('previews new points and saves a future-only version with a reason', async () => {
    const calls = mockApi({
      'GET /api/seasons/4/rules': () => json(200, { can_edit: true, versions: [version] }),
      'POST /api/seasons/4/rules/preview': () =>
        json(200, [{ entry_id: 1, driver_name: 'Ana', current_rank: 2, current_points: 40, new_rank: 1, new_points: 18 }]),
      'POST /api/seasons/4/rules': () => json(200, { can_edit: true, versions: [{ ...version, number: 2 }, version] }),
    })
    renderPage(<RulesSection seasonId={4} adminView />, { path: '/seasons/:seasonId', url: '/seasons/4' })
    expect(await screen.findByText('Puntos por puesto')).toBeInTheDocument()
    expect(screen.getByRole('list')).toHaveTextContent('P125P218P315')

    await userEvent.click(screen.getByRole('button', { name: 'Cambiar el reglamento' }))
    const points = screen.getByLabelText('Puntos por posición (separados por coma)')
    await userEvent.clear(points)
    await userEvent.type(points, '10, 8, 6')
    await userEvent.click(screen.getByRole('button', { name: 'Ver cómo queda la tabla' }))
    expect(await screen.findByText('P1 · 18 pts')).toHaveClass('faster')
    expect(calls.find((c) => c.key === 'POST /api/seasons/4/rules/preview')!.body).toMatchObject({ points_by_position: [10, 8, 6] })

    await userEvent.type(screen.getByLabelText('Motivo del cambio'), 'Menos puntos')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar versión nueva' }))
    expect(await screen.findByText('Reglamento guardado.')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/seasons/4/rules')!.body).toMatchObject({ reason: 'Menos puntos', recalculate: false })
  })

  it('shows only the rules to a driver', async () => {
    mockApi({ 'GET /api/seasons/4/rules': () => json(200, { can_edit: false, versions: [version] }) })
    renderPage(<RulesSection seasonId={4} adminView={false} />, { path: '/seasons/:seasonId', url: '/seasons/4' })
    expect(await screen.findByText('10/10/5/3 kg · máx. 45 kg')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cambiar el reglamento' })).not.toBeInTheDocument()
  })
})
