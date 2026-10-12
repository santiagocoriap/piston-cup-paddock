import { useTranslation } from 'react-i18next'
import { currentTimeZone, formatDateTime, sameClock } from '../lib/format'

/** The race time in the timezone of the user, and the event time when the clock differs. */
export function EventTime({ iso, eventTimeZone }: { iso: string | null | undefined; eventTimeZone: string }) {
  const { t, i18n } = useTranslation()
  if (!iso) return <>{t('briefing.noDate')}</>
  const own = formatDateTime(iso, i18n.language)
  if (sameClock(iso, currentTimeZone(), eventTimeZone)) return <>{own}</>
  return (
    <>
      {own}
      <span className="event-time">
        {t('briefing.eventTime', {
          time: formatDateTime(iso, i18n.language, eventTimeZone),
          zone: eventTimeZone.replaceAll('_', ' '),
        })}
      </span>
    </>
  )
}
