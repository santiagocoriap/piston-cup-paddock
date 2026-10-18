import { currentTimeZone } from './format'

/** The day of a moment in the user timezone, as YYYY-MM-DD, so days sort and compare as text. */
export function dayKey(iso: string | Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: currentTimeZone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(iso))
}

/** Today and yesterday as day keys. Read them once, when a page opens. */
export function nearDays(now: number): { today: string; yesterday: string } {
  return { today: dayKey(new Date(now)), yesterday: dayKey(new Date(now - 86_400_000)) }
}

/** "Hoy", "Ayer", or the full date of a day key. */
export function dayTitle(
  day: string,
  near: { today: string; yesterday: string },
  language: string,
  labels: { today: string; yesterday: string },
): string {
  if (day === near.today) return labels.today
  if (day === near.yesterday) return labels.yesterday
  // Noon UTC keeps the same calendar day in every timezone.
  return new Intl.DateTimeFormat(language, { dateStyle: 'full', timeZone: 'UTC' }).format(new Date(`${day}T12:00:00Z`))
}
