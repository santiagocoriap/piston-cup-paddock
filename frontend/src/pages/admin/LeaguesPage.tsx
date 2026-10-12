import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { ActionForm } from '../../components/ActionForm'
import { Loading } from '../../components/Layout'
import { useLoad } from '../../lib/useLoad'

export function LeaguesPage() {
  const { t } = useTranslation()
  const leagues = useLoad(() => api.GET('/api/leagues'), [])

  if (!leagues.data) return <Loading failed={leagues.failed} />
  return (
    <section>
      <h1>{t('leagues.title')}</h1>
      {leagues.data.length === 0 && <p>{t('leagues.empty')}</p>}
      <ul className="list">
        {leagues.data.map((league) => (
          <li key={league.id}>{league.name}</li>
        ))}
      </ul>
      <div className="forms">
        <ActionForm
          title={t('leagues.newLeague')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/leagues', {
              body: { name: String(form.get('name')) },
            })
            if (!error) leagues.reload()
            return error
          }}
        >
          <label>
            {t('common.name')}
            <input name="name" required maxLength={100} />
          </label>
        </ActionForm>
        <ActionForm
          title={t('leagues.newChampionship')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/leagues/{league_id}/championships', {
              params: { path: { league_id: Number(form.get('league_id')) } },
              body: { name: String(form.get('name')) },
            })
            return error
          }}
        >
          <label>
            {t('leagues.league')}
            <select name="league_id" required defaultValue="">
              <option value="" disabled>
                {t('common.select')}
              </option>
              {leagues.data.map((league) => (
                <option key={league.id} value={league.id}>
                  {league.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('common.name')}
            <input name="name" required maxLength={100} />
          </label>
        </ActionForm>
      </div>
    </section>
  )
}
