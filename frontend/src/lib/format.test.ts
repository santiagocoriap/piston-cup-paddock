import { afterEach, describe, expect, it } from 'vitest'
import { formatDateTime, localInputToIso, offsetMinutes, sameClock, setDisplayTimeZone } from './format'

afterEach(() => setDisplayTimeZone(undefined))

describe('timezones', () => {
  it('shows a race time in the timezone of the user', () => {
    setDisplayTimeZone('America/Argentina/Buenos_Aires')
    expect(formatDateTime('2026-10-19T00:30:00Z', 'en-GB')).toContain('21:30')
    setDisplayTimeZone('Europe/Madrid')
    expect(formatDateTime('2026-10-19T00:30:00Z', 'en-GB')).toContain('02:30')
  })

  it('reads a datetime-local value in the timezone of the user', () => {
    expect(localInputToIso('2026-10-18T21:30', 'America/Argentina/Buenos_Aires')).toBe('2026-10-18T21:30:00-03:00')
    expect(localInputToIso('2026-07-01T20:00', 'Europe/Madrid')).toBe('2026-07-01T20:00:00+02:00')
    expect(localInputToIso('2026-12-01T20:00', 'Europe/Madrid')).toBe('2026-12-01T20:00:00+01:00')
  })

  it('knows when two zones show the same clock', () => {
    expect(sameClock('2026-10-19T00:30:00Z', 'America/Argentina/Buenos_Aires', 'America/Sao_Paulo')).toBe(true)
    expect(sameClock('2026-10-19T00:30:00Z', 'America/Argentina/Buenos_Aires', 'Europe/Madrid')).toBe(false)
    expect(offsetMinutes('UTC', Date.UTC(2026, 0, 1))).toBe(0)
  })
})
