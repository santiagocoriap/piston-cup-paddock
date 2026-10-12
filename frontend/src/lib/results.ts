import type { components } from '../api/schema'

type LineOut = components['schemas']['LineOut']

/** A penalty changed this line when the final value differs from the entered value. */
export function penaltyChanged(line: LineOut): boolean {
  return (
    line.entered_status !== line.status ||
    (line.entered_position ?? null) !== (line.position ?? null)
  )
}
