import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { EngineerSection } from './EngineerSection'

afterEach(() => vi.restoreAllMocks())

const lap = (id: number, driver_name: string, own: boolean) => ({ id, driver_name, lap_number: id, lap_time_ms: 180000 + id, own })

describe('EngineerSection', () => {
  it('shows the reference, the evidence, a test, and the setup limit', async () => {
    mockApi({
      'GET /api/rounds/9/engineer': () =>
        json(200, {
          reference: lap(1, 'Fast', false),
          laps: [lap(2, 'Slow', true), lap(3, 'Slow', true)],
          lap_length_m: 5000,
          zones: 4,
          advice: [
            { kind: 'brake_later', zone: 2, position: 0.3, reference_value: 0, lap_values: [48, 52], difference: 50, laps_showing: 2, laps_total: 2 },
          ],
          setup_missing: ['setup', 'fuel'],
          gaps: [],
        }),
    })
    renderPage(<EngineerSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    expect(await screen.findByText(/Referencia: Fast, vuelta 1/)).toBeInTheDocument()
    expect(screen.getByText('Frenada 2 (al 30 % de la vuelta)')).toBeInTheDocument()
    expect(screen.getByText(/50 m antes que la referencia, en 2 de 2 vueltas/)).toBeInTheDocument()
    expect(screen.getByText(/48 · 52 m antes/)).toBeInTheDocument()
    expect(screen.getByText(/frená 10 m más tarde/)).toBeInTheDocument()
    expect(screen.getByText(/no por qué/)).toBeInTheDocument()
    expect(screen.getByText(/Consejos de setup: apagados. Hacen falta datos de setup, combustible/)).toBeInTheDocument()
  })

  it('stays hidden without own laps', async () => {
    mockApi({
      'GET /api/rounds/9/engineer': () =>
        json(200, { reference: null, laps: [], lap_length_m: null, zones: 0, advice: [], setup_missing: [], gaps: ['not_enough_laps'] }),
    })
    const { container } = renderPage(<EngineerSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
