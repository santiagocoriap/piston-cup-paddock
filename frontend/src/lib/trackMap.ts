/** A track drawing from the recorded positions, and the scale of a map in an SVG box. */

type Trail = { x: number[]; z: number[] }
export type Point = { x: number; z: number }

/** The drawing of the track: the full lap of the round track map. Without it, the trail of the
 * car with the most samples. Empty without data. */
export function trackOutline(map: { x: number[]; z: number[] } | null | undefined, cars: Trail[]): Point[] {
  // The map ends just before the line. Back to the first point closes the lap.
  if (map && map.x.length >= 10) return [...map.x, map.x[0]].map((x, i) => ({ x, z: map.z[i % map.z.length] }))
  return outlineOf(cars)
}

/** The trail of the car with the most samples. Empty without data. */
export function outlineOf(cars: Trail[]): Point[] {
  const longest = cars.reduce<Trail | null>((best, car) => (!best || car.x.length > best.x.length ? car : best), null)
  return longest ? longest.x.map((x, i) => ({ x, z: longest.z[i] })) : []
}

/** The SVG points of a list of world points. */
export function polyline(points: Point[], place: (p: Point) => [number, number]): string {
  return points.map((p) => place(p).join(',')).join(' ')
}

/** A function that puts a world point into a square box of this size, with a margin. All the
 * points fit, and the scale is the same on both axes. */
export function fit(points: Point[], size: number, margin: number): (p: Point) => [number, number] {
  if (points.length === 0) return () => [size / 2, size / 2]
  const xs = points.map((p) => p.x)
  const zs = points.map((p) => p.z)
  const [minX, maxX, minZ, maxZ] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)]
  const span = Math.max(maxX - minX, maxZ - minZ, 1)
  const scale = (size - 2 * margin) / span
  // Center the drawing in the box.
  const offsetX = margin + (size - 2 * margin - (maxX - minX) * scale) / 2
  const offsetZ = margin + (size - 2 * margin - (maxZ - minZ) * scale) / 2
  return (p) => [offsetX + (p.x - minX) * scale, offsetZ + (p.z - minZ) * scale]
}
