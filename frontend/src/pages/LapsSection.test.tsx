import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { LapsSection } from './LapsSection'

afterEach(() => vi.restoreAllMocks())

const lap = (lap_number: number, time_ms: number, extra = {}) => ({
  lap_number, time_ms, sectors_ms: [60000, 70000, time_ms - 130000], valid: true, cuts: 0, invalid_reason: '',
  tyre: 'H', pit: null, time_mark: null, sector_marks: [null, null, null], ...extra,
})

const average = (ms: number, laps: number, excluded = {}) => ({ ms, laps, excluded })

const data = (session: string) => ({
  session,
  sessions: ['race', 'qualifying'],
  has_sectors: true,
  has_pit_data: true,
  clean_rules: ['invalid', 'pit_in', 'pit_out', 'first_lap'],
  drivers: [
    {
      entry_id: 1, driver_name: 'Driver 01', number: 2, best_lap_ms: 189296, best_lap_number: 2,
      average: average(195000, 3), clean_average: average(190000, 1, { first_lap: 1 }),
      theoretical_ms: 188000, best_sectors_ms: [60000, 70000, 58000],
      laps: [
        lap(1, 200000),
        lap(2, 189296, { time_mark: 'session', sector_marks: ['session', null, 'personal'] }),
        lap(3, 210000, { pit: 'in' }),
        lap(4, 199000, { valid: false, cuts: 2 }),
      ],
    },
  ],
})

describe('LapsSection', () => {
  it('shows marks, averages with counts, the theoretical label, and pit laps', async () => {
    const sessions: string[] = []
    mockApi({
      'GET /api/rounds/9/laps': (request) => {
        const session = new URL(request.url).searchParams.get('session') ?? 'race'
        sessions.push(session)
        return json(200, data(session))
      },
    })
    renderPage(<LapsSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9' })
    expect(await screen.findByRole('heading', { name: 'Vueltas' })).toBeInTheDocument()
    expect(screen.getByText('Teórica')).toBeInTheDocument()
    expect(screen.getByText(/la vuelta 1 \(largada\)/)).toBeInTheDocument()
    expect(screen.getAllByLabelText('Mejor de la sesión').length).toBeGreaterThan(0)
    expect(screen.getByRole('img', { name: 'Tiempo de vuelta por vuelta' })).toBeInTheDocument()

    await userEvent.click(screen.getByText(/Driver 01 · 4 vueltas/))
    const table = screen.getByRole('table', { name: 'Vueltas de Driver 01' })
    expect(within(table).getByText('Entrada')).toBeInTheDocument()
    expect(within(table).getByText('✕ 2 cortes')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Clasificación' }))
    await vi.waitFor(() => expect(sessions).toContain('qualifying'))
  })
})
