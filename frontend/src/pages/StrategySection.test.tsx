import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { StrategySection } from './StrategySection'

afterEach(() => vi.restoreAllMocks())

const stint = (number: number, tyre: string, first: number, last: number, endsInPit: boolean) => ({
  number, tyre, first_lap: first, last_lap: last, laps: last - first + 1,
  best_ms: 90_000 + number, average_ms: 91_000, ends_in_pit: endsInPit,
})

const driver = (entryId: number, name: string, stints: ReturnType<typeof stint>[]) => ({
  entry_id: entryId, driver_name: name, number: entryId, best_lap_ms: 90_000, best_lap_number: 2,
  average: { ms: null, laps: 0, excluded: {} }, clean_average: { ms: null, laps: 0, excluded: {} },
  theoretical_ms: null, best_sectors_ms: [], laps: [], stints,
})

describe('StrategySection', () => {
  it('shows the stints of each driver in the order of the result, with the tyres', async () => {
    mockApi({
      'GET /api/rounds/9/laps': () =>
        json(200, {
          session: 'race', sessions: ['race'], has_sectors: false, has_pit_data: true, clean_rules: [],
          drivers: [
            driver(2, 'Vice', [stint(1, 'M', 1, 10, false)]),
            driver(1, 'Bing', [stint(1, 'S', 1, 4, true), stint(2, 'H', 5, 10, false)]),
          ],
        }),
    })
    renderPage(<StrategySection roundId={9} order={[1, 2]} />, { path: '/rounds/:roundId', url: '/rounds/9' })
    const rows = await screen.findAllByRole('list', { name: /^Stints de / })
    expect(rows.map((row) => row.getAttribute('aria-label'))).toEqual(['Stints de Bing', 'Stints de Vice'])
    const bing = within(rows[0]).getAllByRole('listitem')
    expect(bing.map((block) => block.getAttribute('aria-label'))).toEqual([
      'Stint 1: S, vueltas 1 a 4 (4 vueltas) · mejor 1:30.001 · promedio 1:31.000',
      'Stint 2: H, vueltas 5 a 10 (6 vueltas) · mejor 1:30.002 · promedio 1:31.000',
    ])
    expect(bing[0]).toHaveClass('tyre-soft')
    expect(screen.getByText('1 parada')).toBeInTheDocument()
    expect(screen.getByText('0 paradas')).toBeInTheDocument()
  })

  it('shows nothing for a race without laps', async () => {
    mockApi({
      'GET /api/rounds/9/laps': () =>
        json(200, { session: 'race', sessions: [], has_sectors: false, has_pit_data: false, clean_rules: [], drivers: [] }),
    })
    const { container } = renderPage(<StrategySection roundId={9} order={[]} />, { path: '/rounds/:roundId', url: '/rounds/9' })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
