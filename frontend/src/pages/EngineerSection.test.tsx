import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { EngineerSection } from './EngineerSection'

afterEach(() => vi.restoreAllMocks())

const lap = (id: number, driver_name: string, time: number) => ({ id, driver_name, lap_number: id, lap_time_ms: time })
const metrics = (brake: number, min: number) => ({
  time_s: 12, brake_m: brake, brake_peak: 90, min_kmh: min, apex_m: 500, throttle_m: 600, coast_m: 0, exit_kmh: 120, gear: 2,
})
const empty = {
  driver: { id: 2, name: 'Slow' }, drivers: [], session: 'race', laps: [], lap: null, reference: null,
  reference_options: [], length_m: null, has_pedals: false, ideal_s: null, corners: [], spread: [], note: null,
  ai_available: true, gaps: [] as string[],
}
const map = { length_m: 5000, spline: [], x: [], z: [] }

function engineer(extra = {}) {
  return {
    ...empty,
    laps: [lap(2, 'Slow', 101_000), lap(3, 'Slow', 102_000)],
    lap: lap(2, 'Slow', 101_000),
    reference: lap(1, 'Fast', 100_000),
    reference_options: [lap(1, 'Fast', 100_000)],
    length_m: 5000,
    has_pedals: true,
    ideal_s: 100.5,
    corners: [
      {
        number: 1, start: 0, apex: 0.1, end: 0.3, loss_s: 0.8, reference_lap_id: 1,
        yours: metrics(400, 90), reference: metrics(450, 98),
        causes: [
          { kind: 'brake_early', yours: 400, reference: 450, difference: -50 },
          { kind: 'min_speed', yours: 90, reference: 98, difference: -8 },
        ],
      },
      {
        number: 2, start: 0.3, apex: 0.5, end: 1, loss_s: -0.1, reference_lap_id: 1,
        yours: metrics(1500, 70), reference: metrics(1500, 70), causes: [],
      },
    ],
    ...extra,
  }
}

describe('EngineerSection', () => {
  it('shows where to gain time, why, and what to try', async () => {
    mockApi({
      'GET /api/rounds/9/engineer': () => json(200, engineer()),
      'GET /api/rounds/9/track-map': () => json(200, map),
    })
    renderPage(<EngineerSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    const card = (await screen.findByText('+0.80 s', { selector: '.eng-loss' })).closest('article') as HTMLElement
    expect(within(card).getByText('Curva 1')).toBeInTheDocument()
    expect(within(card).getByText('Empezás a frenar 50 m antes que la referencia.')).toBeInTheDocument()
    expect(within(card).getByText('Probá frenar 5 a 10 m más tarde por vez.')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Ver en la telemetría/ })).toHaveAttribute(
      'href',
      '/rounds/9?tab=telemetry&laps=2,1&ref=1&from=0.0000&to=0.3100',
    )
    // Corner 2 is faster: no card for it.
    expect(screen.queryByText('+-0.10 s')).not.toBeInTheDocument()
    expect(screen.getByText('Tu vuelta ideal')).toBeInTheDocument()
  })

  it('asks the AI for a note', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/engineer': () => json(200, engineer()),
      'GET /api/rounds/9/track-map': () => json(200, map),
      'POST /api/rounds/9/engineer/note': () =>
        json(200, { id: 1, status: 'pending', text: '', error: '', created_at: '2026-10-15T20:00:00Z' }),
    })
    renderPage(<EngineerSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    await userEvent.click(await screen.findByRole('button', { name: 'Pedir el resumen' }))
    const body = calls.find((c) => c.key === 'POST /api/rounds/9/engineer/note')!.body as { session: string; language: string }
    expect(body).toMatchObject({ session: 'race', language: 'es' })
  })

  it('says why the tab is empty without own laps', async () => {
    mockApi({
      'GET /api/rounds/9/engineer': () => json(200, { ...empty, gaps: ['no_laps'] }),
      'GET /api/rounds/9/track-map': () => json(200, map),
    })
    renderPage(<EngineerSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    expect(await screen.findByText(/Una vuelta con un corte no cuenta/)).toBeInTheDocument()
  })

  it('asks for a driver profile when the account has none', async () => {
    mockApi({
      'GET /api/rounds/9/engineer': () => json(200, { ...empty, driver: null, gaps: ['no_driver'] }),
      'GET /api/rounds/9/track-map': () => json(200, map),
    })
    renderPage(<EngineerSection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    expect(await screen.findByRole('link', { name: /Inicio|inicio/ })).toBeInTheDocument()
  })
})
