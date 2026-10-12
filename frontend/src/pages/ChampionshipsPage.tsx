import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import { Loading } from '../components/Layout'
import { useLoad } from '../lib/useLoad'

export function ChampionshipsPage() {
  const { t } = useTranslation()
  const { data, failed } = useLoad(() => api.GET('/api/championships'), [])

  if (!data) return <Loading failed={failed} />
  return (
    <section>
      <h1>{t('championships.title')}</h1>
      {data.length === 0 && <p>{t('championships.empty')}</p>}
      <ul className="list">
        {data.map((championship) => (
          <li key={championship.id}>
            <Link to={`/championships/${championship.id}`}>{championship.name}</Link>
            <span className="muted"> · {championship.league_name}</span>
            {championship.can_manage && <span className="badge">{t('championships.adminBadge')}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}
