/** Show a date and time in the timezone of the browser. */
export function formatDateTime(iso: string, language: string): string {
  return new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

/** Turn the value of a datetime-local input into an ISO string with the browser offset. */
export function localInputToIso(value: string): string {
  const date = new Date(value)
  const offset = -date.getTimezoneOffset()
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
