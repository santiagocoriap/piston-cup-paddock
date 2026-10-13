import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon, type IconName } from '../components/Icon'
import { Loading } from '../components/Layout'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useMe, useMode } from '../session'
import { DashboardSection } from './DashboardSection'

type Championship = components['schemas']['ChampionshipOut']
type PendingKind = components['schemas']['PendingOut']
type PendingItem = components['schemas']['PendingItemOut']

/** The home page: the dashboard of the driver, what waits for an admin, and the championships. */
export function ChampionshipsPage() {
  const { t } = useTranslation()
  const { data, failed } = useLoad(() => api.GET('/api/championships'), [])

  return (
    <>
      <DashboardSection />
      <PendingSection />
      <section aria-labelledby="championships">
        <h2 id="championships">{t('championships.title')}</h2>
        {!data && <Loading failed={failed} />}
        {data?.length === 0 && <p className="muted">{t('championships.empty')}</p>}
        <ul className="champ-grid">
          {data?.map((championship) => (
            <ChampionshipCard key={championship.id} championship={championship} />
          ))}
        </ul>
      </section>
    </>
  )
}

function ChampionshipCard({ championship }: { championship: Championship }) {
  const { t, i18n } = useTranslation()
  const [now] = useState(() => Date.now())
  const detail = useLoad(
    () =>
      api.GET('/api/championships/{championship_id}', {
        params: { path: { championship_id: championship.id } },
      }),
    [championship.id],
  )
  const latest = detail.data?.latest
  const seasons = detail.data?.seasons ?? []
  const next = latest?.next_round
  return (
    <li className="champ-card">
      <div className="champ-head">
        <span className="champ-icon">
          <Icon name="trophy" />
        </span>
        <div>
          <h3>
            <Link to={`/championships/${championship.id}`}>{championship.name}</Link>
          </h3>
          <p className="muted">{championship.league_name}</p>
        </div>
        {championship.can_manage && <span className="flat-badge">{t('championships.adminBadge')}</span>}
      </div>
      {detail.data &&
        (latest ? (
          <div className="champ-status">
            <p className="champ-season">
              <b>{latest.name}</b>
              <span className="muted"> · {t('championships.progress', { done: latest.done, total: latest.total })}</span>
              {seasons.length > 1 && (
                <span className="muted"> · {t('championships.moreSeasons', { count: seasons.length - 1 })}</span>
              )}
            </p>
            <div className="champ-progress" aria-hidden="true">
              <span style={{ width: `${Math.min(100, (latest.done / Math.max(1, latest.total)) * 100)}%` }} />
            </div>
            {next ? (
              <p className="champ-next">
                <Icon name="flag" small />
                <span>
                  {t('championships.next', { number: next.number, track: `${next.track_name} · ${next.layout_name}` })}
                  <span className="muted">
                    {' · '}
                    {next.scheduled_at
                      ? `${formatDateTime(next.scheduled_at, i18n.language)} (${relativeTime(next.scheduled_at, now, i18n.language)})`
                      : t('championships.noDate')}
                  </span>
                </span>
              </p>
            ) : (
              <p className="muted champ-next">{t('championships.noNext')}</p>
            )}
            {latest.leader && (
              <p className="champ-leader">
                <Icon name="trophy" small />
                {t('championships.leader', { name: latest.leader })}
              </p>
            )}
          </div>
        ) : (
          <p className="muted champ-season">{t('championship.noSeasons')}</p>
        ))}
      <Link className="small-link" to={`/championships/${championship.id}`}>
        {t('championships.open')}
        <Icon name="arrow" small />
      </Link>
    </li>
  )
}

/** "in 5 days" or "in 3 hours", in the language of the user. */
function relativeTime(iso: string, now: number, language: string): string {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60_000)
  const format = new Intl.RelativeTimeFormat(language, { numeric: 'auto' })
  if (Math.abs(minutes) < 60) return format.format(minutes, 'minute')
  if (Math.abs(minutes) < 60 * 24) return format.format(Math.round(minutes / 60), 'hour')
  return format.format(Math.round(minutes / 1440), 'day')
}

const PENDING_ICONS: Record<string, IconName> = {
  results: 'flag',
  protests: 'alert',
  ballots_closed: 'layers',
  ballots_open: 'layers',
  accounts: 'shield',
  images: 'map',
}

// A kind with no list of items links to the page that holds the items.
const PENDING_PAGES: Record<string, string> = {
  accounts: '/admin/accounts',
  images: '/admin/catalog?tab=images',
}

/** In the admin mode, what waits for the admin: results, protests, ballots, accounts, images. */
function PendingSection() {
  const { t } = useTranslation()
  const me = useMe()
  const { mode } = useMode()
  const show = mode === 'admin' && (me.is_admin || me.can_manage)
  const pending = useLoad(
    () => (show ? api.GET('/api/pending') : Promise.resolve({ data: [] as PendingKind[] })),
    [show],
  )
  if (!show) return null
  return (
    <section aria-labelledby="pending">
      <h2 id="pending">{t('home.pending.title')}</h2>
      {!pending.data ? (
        <Loading failed={pending.failed} />
      ) : pending.data.length === 0 ? (
        <p className="pending-none">
          <Icon name="check" small />
          {t('home.pending.none')}
        </p>
      ) : (
        <ul className="pending-list">
          {pending.data.map((kind) => (
            <li key={kind.kind} className={`pending-row pending-${kind.kind}`}>
              <span className="pending-icon" aria-hidden="true">
                <Icon name={PENDING_ICONS[kind.kind] ?? 'info'} small />
              </span>
              <div className="pending-body">
                <p className="pending-title">{t(`home.pending.${kind.kind}`, { count: kind.count })}</p>
                {kind.items.length > 0 && (
                  <ul className="pending-items">
                    {kind.items.map((item, index) => (
                      <li key={`${item.path}-${index}`}>
                        <Link to={item.path}>{pendingLabel(t, item)}</Link>
                        {item.championship && <span className="muted"> · {item.championship}</span>}
                      </li>
                    ))}
                    {kind.count > kind.items.length && (
                      <li className="muted">{t('home.pending.more', { count: kind.count - kind.items.length })}</li>
                    )}
                  </ul>
                )}
              </div>
              {PENDING_PAGES[kind.kind] && (
                <Link className="small-link" to={PENDING_PAGES[kind.kind]}>
                  {t('home.pending.open')}
                  <Icon name="arrow" small />
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function pendingLabel(t: (key: string, options?: Record<string, unknown>) => string, item: PendingItem): string {
  return item.number === null ? item.name : `${t('round.title', { number: item.number })} · ${item.name}`
}
