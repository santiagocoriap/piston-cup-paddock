import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { formatDateTime } from '../lib/format'

type Notifications = components['schemas']['NotificationsOut']

const POLL_MS = 60_000

/** The bell in the header: the unread count and the newest notifications. */
export function NotificationBell() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [data, setData] = useState<Notifications | null>(null)
  const [open, setOpen] = useState(false)

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
  return (
    <div className="bell">
      <button
        type="button"
        className="secondary"
        aria-expanded={open}
        aria-label={t('notifications.title', { count: unread })}
        onClick={() => setOpen((o) => !o)}
      >
        🔔{unread > 0 && <span className="bell-count">{unread}</span>}
      </button>
      {open && data && (
        <div className="bell-panel card" role="dialog" aria-label={t('notifications.panel')}>
          {data.items.length === 0 ? (
            <p className="muted">{t('notifications.none')}</p>
          ) : (
            <ul className="list">
              {data.items.map((n) => (
                <li key={n.id} className={n.read ? 'muted' : undefined}>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => {
                      setOpen(false)
                      read([n.id])
                      if (n.link) navigate(n.link)
                    }}
                  >
                    {t(`notifications.kinds.${n.kind}`, n.params as Record<string, string>)}
                  </button>
                  <span className="muted"> · {formatDateTime(n.created_at, i18n.language)}</span>
                </li>
              ))}
            </ul>
          )}
          {unread > 0 && (
            <button type="button" className="secondary small" onClick={() => read([])}>
              {t('notifications.readAll')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
