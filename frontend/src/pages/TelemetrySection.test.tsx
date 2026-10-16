import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { TelemetrySection } from './TelemetrySection'

// jsdom cannot draw on a canvas. A fake chart keeps the rest of the tool testable.
vi.mock('uplot', () => {
  class FakePlot {
    over = document.createElement('div')
    scales = { x: { min: 0, max: 100 } }
    bbox = { left: 0, top: 0, width: 100, height: 100 }
    constructor(_opts: unknown, _data: unknown, target: HTMLElement) {
      target.appendChild(this.over)
    }
    setScale() {}
    setCursor() {}
    valToPos(value: number) {
      return value
    }
    posToVal(value: number) {
      return value
    }
    destroy() {
      this.over.remove()
    }
    static paths = { stepped: () => () => null }
  }
  return { default: FakePlot }
})

afterEach(() => vi.restoreAllMocks())

// jsdom has no ResizeObserver. The chart reads its width with one.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

const lap = (id: number, driver: string, number: number, time: number, access = 'full') => ({
  id, driver_name: driver, session_type: 'race', lap_number: number, lap_time_ms: time, valid: true, access,
  attempt_number: 1,
})
const channels = (speed: number) => ({
  t_ms: [0, 50_000, 100_000], pos: [0, 0.5, 1], speed_kmh: [speed, 120, speed],
  gas: [1, 0, 1], brake: [0, 1, 0], steer: [0, -40, 10], gear: [5, 3, 6], rpm: [7000, 5000, 8000],
})

describe('TelemetrySection', () => {
  it('starts with the best lap of each driver and compares them', async () => {
    const laps = [lap(4, 'Ana', 3, 100_000), lap(5, 'Bruno', 2, 99_000), lap(6, 'Ana', 4, 101_000)]
    const calls = mockApi({
      'GET /api/rounds/9/telemetry': () => json(200, laps),
      'GET /api/rounds/9/track-map': () => json(200, { length_m: 2500, spline: [], x: [], z: [] }),
      'GET /api/telemetry-laps/4': () => json(200, { ...laps[0], sample_hz: 20, car: 'tc', channels: channels(200) }),
      'GET /api/telemetry-laps/5': () => json(200, { ...laps[1], sample_hz: 20, car: 'tc', channels: channels(210) }),
      'GET /api/telemetry-laps/6': () => json(200, { ...laps[2], sample_hz: 20, car: 'tc', channels: channels(190) }),
    })
    renderPage(<TelemetrySection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: ADMIN })

    // The best lap of each driver is on the chart. Lap 4 of Ana is not.
    expect(await screen.findByRole('button', { name: /V3/, pressed: true })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /V2/, pressed: true })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /V4/, pressed: false })).toBeInTheDocument()
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Ana')).toBeInTheDocument()
    expect(within(table).getByText(/V2 · REF/)).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'GET /api/telemetry-laps/6')).toBe(false)

    // The faster lap of Bruno is the reference. Ana can become the reference.
    await userEvent.click(screen.getByRole('button', { name: 'Usar Ana · V3 como referencia' }))
    expect(within(table).getByText(/V3 · REF/)).toBeInTheDocument()

    // A third lap goes onto the chart.
    await userEvent.click(screen.getByRole('button', { name: /V4/ }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'GET /api/telemetry-laps/6')).toBe(true))
  })

  it('turns a lane off and on', async () => {
    mockApi({
      'GET /api/rounds/9/telemetry': () => json(200, [lap(4, 'Ana', 3, 100_000)]),
      'GET /api/rounds/9/track-map': () => json(200, { length_m: null, spline: [], x: [], z: [] }),
      'GET /api/telemetry-laps/4': () =>
        json(200, { ...lap(4, 'Ana', 3, 100_000), sample_hz: 20, car: 'tc', channels: channels(200) }),
    })
    renderPage(<TelemetrySection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: ADMIN })
    await screen.findByRole('table')
    expect(screen.getByText('Volante', { selector: '.tm-lane-label' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Volante', pressed: true }))
    expect(screen.queryByText('Volante', { selector: '.tm-lane-label' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Volante', pressed: false }))
    expect(screen.getByText('Volante', { selector: '.tm-lane-label' })).toBeInTheDocument()
  })
})
