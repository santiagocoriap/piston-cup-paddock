import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { CompareSection } from './CompareSection'

afterEach(() => vi.restoreAllMocks())

const lap = (id: number, driver_name: string, lap_time_ms: number, extra = {}) => ({
  id, entry_id: id, driver_name, lap_number: 3, lap_time_ms, valid: true, sectors_ms: [60000, 70000, lap_time_ms - 130000],
  car: 'Acura', ballast_kg: 0, restrictor: 0, tyre: 'H', telemetry: 'none', ...extra,
})

const a = lap(1, 'Driver 03', 190680)
const b = lap(2, 'Driver 01', 189296, { ballast_kg: 10 })
const other = lap(3, 'Driver 06', 197558)

const comparison = (extra = {}) => ({
  session: 'race', choices: [b, a, other], a, b, sector_diff_ms: [0, 0, -1384],
  delta: { pos: [0, 0.5, 1], delta_ms: [0, -500, -1384], coverage: 1 },
  speed_a: null, speed_b: null, conditions: { weather: 'Clear' },
  gaps: ['no_map', 'different_handicaps'], ...extra,
})

describe('CompareSection', () => {
  it('shows the sign, the sector differences, the delta, and the warnings', async () => {
    const queries: string[] = []
    mockApi({
      'GET /api/rounds/9/compare': (request) => {
        queries.push(new URL(request.url).search)
        return json(200, comparison())
      },
    })
    renderPage(<CompareSection roundId={9} sessions={['race']} />, { path: '/rounds/:roundId', url: '/rounds/9' })
    expect(await screen.findByText(/Un número positivo \(\+\) quiere decir que B es más lenta/)).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Comparación de las dos vueltas' })
    expect(within(table).getAllByText('−1.384').at(-1)).toHaveClass('faster')
    expect(within(table).getByText('10 kg')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Diferencia de tiempo a lo largo de la pista' })).toBeInTheDocument()
    expect(screen.getByText(/Los lastres o restrictores son distintos/)).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Vuelta B'), '3')
    await vi.waitFor(() => expect(queries.at(-1)).toContain('b=3'))
    expect(queries.at(-1)).toContain('a=1')
  })
})
