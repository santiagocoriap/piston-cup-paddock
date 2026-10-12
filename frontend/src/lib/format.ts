// The timezone of the signed-in user. SessionProvider sets it. Undefined means the browser zone.
let displayTimeZone: string | undefined

export function setDisplayTimeZone(timeZone: string | null | undefined): void {
  displayTimeZone = timeZone || undefined
}

/** The timezone that the app uses for dates: the user setting, or the browser zone. */
export function currentTimeZone(): string {
  return displayTimeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
}

/** Show a date and time in the timezone of the user. No date gives a dash. */
export function formatDateTime(
  iso: string | null | undefined,
  language: string,
  timeZone: string | undefined = displayTimeZone,
): string {
  if (!iso) return '—'
  return new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short', timeZone }).format(
    new Date(iso),
  )
}

/** The offset of a timezone from UTC, in minutes, at one moment. */
export function offsetMinutes(timeZone: string, utcMs: number): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(utcMs))
  const get = (type: string) => Number(parts.find((part) => part.type === type)?.value)
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'))
  return Math.round((asUtc - utcMs) / 60_000)
}

/** True when two timezones show the same clock time at this moment. */
export function sameClock(iso: string, zoneA: string, zoneB: string): boolean {
  const utc = new Date(iso).getTime()
  return offsetMinutes(zoneA, utc) === offsetMinutes(zoneB, utc)
}

/** Turn the value of a datetime-local input, read in the user timezone, into an ISO string. */
export function localInputToIso(value: string, timeZone: string = currentTimeZone()): string {
  const [day, time] = value.split('T')
  const [year, month, date] = day.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  const wall = Date.UTC(year, month - 1, date, hour, minute)
  // Two passes give the right offset also next to a daylight saving change.
  let offset = offsetMinutes(timeZone, wall)
  offset = offsetMinutes(timeZone, wall - offset * 60_000)
  const sign = offset >= 0 ? '+' : '-'
  const pad = (n: number) => String(Math.floor(Math.abs(n))).padStart(2, '0')
  return `${value}:00${sign}${pad(offset / 60)}:${pad(offset % 60)}`
}

/** Show a time in milliseconds as m:ss.mmm, or h:mm:ss.mmm for one hour or more. */
export function formatLapTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || ms <= 0) return '—'
  const hours = Math.floor(ms / 3_600_000)
  const minutes = Math.floor((ms % 3_600_000) / 60_000)
  const seconds = Math.floor((ms % 60_000) / 1000)
  const millis = ms % 1000
  const tail = `${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${tail}` : `${minutes}:${tail}`
}
