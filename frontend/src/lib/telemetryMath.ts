/** Telemetry laps on one common grid of the lap distance, so that laps of different drivers
 * line up, and the time delta between them. */

export const GRID = 1500
export type Channel = 'speed_kmh' | 'gas' | 'brake' | 'steer' | 'gear' | 'rpm'
export const CHANNELS: Channel[] = ['speed_kmh', 'gas', 'brake', 'steer', 'gear', 'rpm']

export type Lap = { id: number; channels: Record<string, number[]> }
/** A lap on the grid: for each grid point, the value of each channel, or null. */
export type GridLap = { id: number; time: (number | null)[]; values: Record<Channel, (number | null)[]> }

/** The place on the lap of each grid point: 0 is the start line, 1 is the finish line. */
export const grid: number[] = Array.from({ length: GRID }, (_, i) => i / (GRID - 1))

/** The lap distance of each sample, always going up. A lap that starts before the line (a car
 * on the grid) starts below 0, and each crossing of the line adds one lap. */
export function unwrap(pos: number[]): number[] {
  const out: number[] = []
  let offset = pos.length > 0 && pos[0] > 0.5 ? -1 : 0
  let top = -Infinity
  pos.forEach((p, i) => {
    if (i > 0 && pos[i - 1] - p > 0.5) offset += 1
    // A car that goes back (a spin) keeps the last value, so the distance only goes up.
    top = Math.max(top, p + offset)
    out.push(top)
  })
  return out
}

/** Linear values at each grid point. "step" keeps the value of the sample before (the gear). */
function sample(pos: number[], values: number[], step: boolean): (number | null)[] {
  const out: (number | null)[] = []
  let j = 0
  for (const s of grid) {
    if (pos.length === 0 || s < pos[0] || s > pos[pos.length - 1]) {
      out.push(null)
      continue
    }
    while (j < pos.length - 2 && pos[j + 1] < s) j++
    const [p0, p1] = [pos[j], pos[j + 1] ?? pos[j]]
    const [v0, v1] = [values[j], values[j + 1] ?? values[j]]
    if (v0 === undefined) {
      out.push(null)
    } else if (step || p1 === p0) {
      out.push(s >= p1 ? v1 : v0)
    } else {
      out.push(v0 + ((v1 - v0) * (s - p0)) / (p1 - p0))
    }
  }
  return out
}

/** A lap on the common grid. Pedals become percents. */
export function toGrid(lap: Lap): GridLap {
  const pos = unwrap(lap.channels.pos ?? [])
  const values = {} as Record<Channel, (number | null)[]>
  for (const channel of CHANNELS) {
    const raw = lap.channels[channel]
    if (!raw || raw.length !== pos.length) {
      values[channel] = grid.map(() => null)
      continue
    }
    const scaled = channel === 'gas' || channel === 'brake' ? raw.map((v) => v * 100) : raw
    values[channel] = sample(pos, scaled, channel === 'gear')
  }
  const times = lap.channels.t_ms ?? []
  const time = times.length === pos.length ? sample(pos, times, false) : grid.map(() => null)
  return { id: lap.id, time, values }
}

/** The time of a lap at each grid point, in seconds from the start line. */
function elapsed(lap: GridLap): (number | null)[] {
  const first = lap.time.find((t) => t !== null) ?? null
  return lap.time.map((t) => (t === null || first === null ? null : (t - first) / 1000))
}

/** The time difference with the reference lap at each grid point, in seconds. A positive value
 * means that the lap is behind the reference. */
export function delta(lap: GridLap, reference: GridLap): (number | null)[] {
  const mine = elapsed(lap)
  const theirs = elapsed(reference)
  return mine.map((t, i) => (t === null || theirs[i] === null ? null : t - (theirs[i] as number)))
}

/** The fastest lap in each part of the track, by the time that each lap takes for the part.
 * Null for a part where a lap has no time. */
export function fastestByPart(laps: GridLap[], parts: number): (number | null)[] {
  const times = laps.map(elapsed)
  const size = Math.floor(GRID / parts)
  return Array.from({ length: parts }, (_, part) => {
    const [a, b] = [part * size, Math.min(GRID - 1, (part + 1) * size)]
    let best: number | null = null
    let bestTime = Infinity
    times.forEach((t, index) => {
      if (t[a] === null || t[b] === null) return
      const spent = (t[b] as number) - (t[a] as number)
      if (spent < bestTime) {
        bestTime = spent
        best = index
      }
    })
    return best
  })
}

/** The x and z of a lap distance, from the track map (points in lap order). */
export function pointAt(map: { spline: number[]; x: number[]; z: number[] }, s: number): { x: number; z: number } | null {
  const { spline, x, z } = map
  if (spline.length === 0) return null
  if (s <= spline[0]) return { x: x[0], z: z[0] }
  for (let i = 1; i < spline.length; i++) {
    if (spline[i] >= s) {
      const share = (s - spline[i - 1]) / (spline[i] - spline[i - 1] || 1)
      return { x: x[i - 1] + (x[i] - x[i - 1]) * share, z: z[i - 1] + (z[i] - z[i - 1]) * share }
    }
  }
  return { x: x[x.length - 1], z: z[z.length - 1] }
}
