import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import { Loading } from '../components/Layout'
import { useLoad } from '../lib/useLoad'
import { DashboardSection } from './DashboardSection'

/** The home page: the dashboard of the driver, then the championships. */
export function ChampionshipsPage() {
  const { t } = useTranslation()
  const { data, failed } = useLoad(() => api.GET('/api/championships'), [])

  return (
    <>
      <DashboardSection />
      <section>
        <h2>{t('championships.title')}</h2>
        {!data && <Loading failed={failed} />}
        {data?.length === 0 && <p>{t('championships.empty')}</p>}
        <ul className="list">
          {data?.map((championship) => (
            <li key={championship.id}>
              <Link to={`/championships/${championship.id}`}>{championship.name}</Link>
              <span className="muted"> · {championship.league_name}</span>
              {championship.can_manage && <span className="badge">{t('championships.adminBadge')}</span>}
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
