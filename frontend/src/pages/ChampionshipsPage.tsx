import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon, type IconName } from '../components/Icon'
import { Loading } from '../components/Layout'
import { useLoad } from '../lib/useLoad'
import { useMe, useMode } from '../session'
import { DashboardSection } from './DashboardSection'

type Championship = components['schemas']['ChampionshipOut']

/** The home page: the dashboard of the driver, the championships, and the admin shortcuts. */
export function ChampionshipsPage() {
  const { t } = useTranslation()
  const { data, failed } = useLoad(() => api.GET('/api/championships'), [])

  return (
    <>
      <DashboardSection />
      <AdminShortcuts />
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
  const { t } = useTranslation()
  const detail = useLoad(
    () =>
      api.GET('/api/championships/{championship_id}', {
        params: { path: { championship_id: championship.id } },
      }),
    [championship.id],
  )
  const seasons = detail.data?.seasons ?? []
  const latest = seasons[seasons.length - 1]
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
        {championship.can_manage && <span className="badge">{t('championships.adminBadge')}</span>}
      </div>
      {detail.data &&
        (latest ? (
          <p className="champ-season">
            <Link to={`/seasons/${latest.id}`}>{latest.name}</Link>
            <span className="muted">
              {' · '}
              {t('season.plannedRounds', { count: latest.planned_round_count })}
            </span>
            {seasons.length > 1 && (
              <span className="muted"> · {t('championships.moreSeasons', { count: seasons.length - 1 })}</span>
            )}
          </p>
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

/** In the admin mode, the admin pages one click from home. */
function AdminShortcuts() {
  const { t } = useTranslation()
  const me = useMe()
  const { mode } = useMode()
  if (mode !== 'admin' || !(me.is_admin || me.can_manage)) return null
  const items: { to: string; icon: IconName; label: string; help: string }[] = []
  if (me.is_admin) {
    items.push({ to: '/admin/leagues', icon: 'layers', label: t('nav.leagues'), help: t('home.shortcuts.leagues') })
    items.push({ to: '/admin/drivers', icon: 'users', label: t('nav.drivers'), help: t('home.shortcuts.drivers') })
    items.push({ to: '/admin/catalog', icon: 'map', label: t('nav.catalog'), help: t('home.shortcuts.catalog') })
  }
  if (me.can_manage) {
    items.push({ to: '/admin/accounts', icon: 'shield', label: t('nav.accounts'), help: t('home.shortcuts.accounts') })
    items.push({ to: '/admin/audit', icon: 'history', label: t('nav.audit'), help: t('home.shortcuts.audit') })
  }
  return (
    <section aria-labelledby="shortcuts">
      <h2 id="shortcuts">{t('home.shortcuts.title')}</h2>
      <ul className="shortcut-grid">
        {items.map((item) => (
          <li key={item.to}>
            <Link className="shortcut" to={item.to}>
              <span className="champ-icon">
                <Icon name={item.icon} />
              </span>
              <span>
                <b>{item.label}</b>
                <span className="muted">{item.help}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
