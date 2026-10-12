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
