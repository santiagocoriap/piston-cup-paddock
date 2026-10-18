import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { dayKey, dayTitle, nearDays } from '../lib/days'
import { currentTimeZone } from '../lib/format'
import { Icon } from './Icon'

type Notifications = components['schemas']['NotificationsOut']

const POLL_MS = 60_000

/** The bell in the header: the unread count and the newest notifications. */
export function NotificationBell() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [data, setData] = useState<Notifications | null>(null)
  const [open, setOpen] = useState(false)
  const [onlyUnread, setOnlyUnread] = useState(false)
  // Today and yesterday, read once, for the day titles.
  const [near] = useState(() => nearDays(Date.now()))

  useEffect(() => {
    let active = true
    const load = () =>
      api.GET('/api/me/notifications').then(
        ({ data: next }) => active && next && setData(next),
        () => undefined,
      )
    load()
    const timer = window.setInterval(load, POLL_MS)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  async function read(ids: number[]) {
    const { data: next } = await api.POST('/api/me/notifications/read', { body: { ids } })
    if (next) setData(next)
  }

  const unread = data?.unread ?? 0
  const shown = (data?.items ?? []).filter((n) => !onlyUnread || !n.read)
  const days: { day: string; items: typeof shown }[] = []
  for (const n of shown) {
    const day = dayKey(n.created_at)
    if (days.at(-1)?.day !== day) days.push({ day, items: [] })
    days.at(-1)!.items.push(n)
  }
  const time = new Intl.DateTimeFormat(i18n.language, { timeStyle: 'short', timeZone: currentTimeZone() })
  const titleOf = (day: string) =>
    dayTitle(day, near, i18n.language, { today: t('audit.today'), yesterday: t('audit.yesterday') })
  return (
    <div className="bell">
      <button
        type="button"
        className="icon-button"
        aria-expanded={open}
        aria-label={t('notifications.title', { count: unread })}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="bell" />
        {unread > 0 && <span className="bell-count">{unread}</span>}
      </button>
      {open && data && (
        <div className="bell-panel card" role="dialog" aria-label={t('notifications.panel')}>
          <div className="bell-head">
            <div className="bell-tabs" role="group" aria-label={t('notifications.panel')}>
              <button type="button" aria-pressed={!onlyUnread} onClick={() => setOnlyUnread(false)}>
                {t('notifications.all')}
              </button>
              <button type="button" aria-pressed={onlyUnread} onClick={() => setOnlyUnread(true)}>
                {t('notifications.unread')}
                {unread > 0 && <span className="tab-count">{unread}</span>}
              </button>
            </div>
            {unread > 0 && (
              <button type="button" className="link" onClick={() => read([])}>
                {t('notifications.readAll')}
              </button>
            )}
          </div>
          {shown.length === 0 ? (
            <p className="muted bell-empty">{onlyUnread ? t('notifications.noneUnread') : t('notifications.none')}</p>
          ) : (
            days.map(({ day, items }) => (
              <section key={day} aria-label={titleOf(day)}>
                <h3 className="bell-day-title">{titleOf(day)}</h3>
                <ul className="bell-list">
                  {items.map((n) => (
                    <li key={n.id} className={n.read ? 'bell-item' : 'bell-item unread'}>
                      <button
                        type="button"
                        onClick={() => {
                          setOpen(false)
                          read([n.id])
                          if (n.link) navigate(n.link)
                        }}
                      >
                        {!n.read && <span className="bell-dot" aria-hidden="true" />}
                        <span className="bell-text">
                          {t(`notifications.kinds.${n.kind}`, n.params as Record<string, string>)}
                        </span>
                        <time className="muted" dateTime={n.created_at}>
                          {time.format(new Date(n.created_at))}
                        </time>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      )}
    </div>
  )
}
