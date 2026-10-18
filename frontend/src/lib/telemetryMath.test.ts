import { describe, expect, it } from 'vitest'
import { GRID, delta, fastestByPart, toGrid, unwrap } from './telemetryMath'

describe('telemetryMath', () => {
  it('moves a sample on the other side of the line by one lap', () => {
    const pos = [0.99, 0.01, 0.2, 0.4, 0.5, 0.6, 0.8, 0.95, 0.99, 0.02]
    const want = [-0.01, 0.01, 0.2, 0.4, 0.5, 0.6, 0.8, 0.95, 0.99, 1.02]
    unwrap(pos).forEach((value, i) => expect(value).toBeCloseTo(want[i], 9))
  })

  it('handles a car that waits on the grid before the line', () => {
    const grid = Array(50).fill(0.998)
    const out = unwrap([...grid, 0.999, 0.002, 0.5, 0.99])
    out.slice(0, 50).forEach((value) => expect(value).toBeCloseTo(-0.002, 9))
    expect(out.slice(-3)).toEqual([0.002, 0.5, 0.99])
  })

  it('keeps the distance going up when the car goes back', () => {
    expect(unwrap([0.1, 0.3, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])).toEqual([
      0.1, 0.3, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95,
    ])
  })

  it('puts a lap on the grid with pedals in percent and the gear in steps', () => {
    const lap = toGrid({
      id: 1,
      channels: { pos: [0, 0.5, 1], t_ms: [0, 50_000, 100_000], speed_kmh: [100, 200, 100], gas: [0, 1, 0], gear: [2, 4, 3] },
    })
    const middle = (GRID - 1) / 2
    expect(lap.values.speed_kmh[0]).toBe(100)
    expect(lap.values.speed_kmh[Math.floor(middle)]).toBeCloseTo(200, -1)
    expect(lap.values.gas[GRID - 1]).toBe(0)
    expect(Math.max(...(lap.values.gas as number[]))).toBeCloseTo(100, 0)
    expect(lap.values.gear[Math.floor(middle / 2)]).toBe(2)
    expect(lap.values.brake.every((v) => v === null)).toBe(true)
  })

  it('gives the time delta with the reference lap', () => {
    const reference = toGrid({ id: 1, channels: { pos: [0, 1], t_ms: [0, 100_000] } })
    const slower = toGrid({ id: 2, channels: { pos: [0, 1], t_ms: [0, 102_000] } })
    const values = delta(slower, reference)
    expect(values[0]).toBe(0)
    expect(values[GRID - 1]).toBeCloseTo(2, 5)
    expect(fastestByPart([slower, reference], 4)).toEqual([1, 1, 1, 1])
  })
})
