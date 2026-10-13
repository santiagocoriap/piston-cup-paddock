import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useLoad } from '../lib/useLoad'

/** The private calendar address of the user, for a phone calendar. */
export function CalendarFeedCard() {
  const { t } = useTranslation()
  const load = useLoad(() => api.GET('/api/me/calendar-feed'), [])
  const [path, setPath] = useState<string | null>(null)
  const current = path ?? load.data?.path
  if (!current) return null
  const url = `${window.location.origin}${current}`

  async function replace() {
    if (!window.confirm(t('calendar.confirmNew'))) return
    const { data } = await api.POST('/api/me/calendar-feed')
    if (data) setPath(data.path)
  }

  return (
    <section className="card" aria-label={t('calendar.feedTitle')}>
      <h2>{t('calendar.feedTitle')}</h2>
      <p className="muted">{t('calendar.feedHelp')}</p>
      <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label={t('calendar.feedAddress')} />
      <button type="button" className="secondary" onClick={replace}>
        {t('calendar.newAddress')}
      </button>
    </section>
  )
}
