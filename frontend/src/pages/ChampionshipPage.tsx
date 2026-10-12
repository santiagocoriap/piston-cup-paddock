import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import { ActionForm } from '../components/ActionForm'
import { Loading } from '../components/Layout'
import { useLoad } from '../lib/useLoad'

export function ChampionshipPage() {
  const { t } = useTranslation()
  const championshipId = Number(useParams().championshipId)
  const path = { championship_id: championshipId }
  const championship = useLoad(
    () => api.GET('/api/championships/{championship_id}', { params: { path } }),
    [championshipId],
  )

  const data = championship.data
  if (!data) return <Loading failed={championship.failed} />
  return (
    <section>
      <p className="muted">{data.league_name}</p>
      <h1>{data.name}</h1>

      <h2>{t('championship.seasons')}</h2>
      {data.seasons.length === 0 && <p>{t('championship.noSeasons')}</p>}
      <ul className="list">
        {data.seasons.map((season) => (
          <li key={season.id}>
            <Link to={`/seasons/${season.id}`}>{season.name}</Link>
            <span className="muted">
              {' '}
              · {t('season.plannedRounds', { count: season.planned_round_count })}
            </span>
          </li>
        ))}
      </ul>

      {data.can_manage && (
        <div className="forms">
          <ActionForm
            title={t('championship.newSeason')}
            submitLabel={t('common.create')}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/championships/{championship_id}/seasons', {
                params: { path },
                body: {
                  name: String(form.get('name')),
                  planned_round_count: Number(form.get('planned_round_count')),
                },
              })
              if (!error) championship.reload()
              return error
            }}
          >
            <label>
              {t('championship.seasonName')}
              <input name="name" required maxLength={100} />
            </label>
            <label>
              {t('championship.plannedRounds')}
              <input name="planned_round_count" type="number" min={1} max={50} required />
            </label>
          </ActionForm>
          <Members championshipId={championshipId} />
        </div>
      )}
    </section>
  )
}

function Members({ championshipId }: { championshipId: number }) {
  const { t } = useTranslation()
  const path = { championship_id: championshipId }
  const members = useLoad(
    () => api.GET('/api/championships/{championship_id}/members', { params: { path } }),
    [championshipId],
  )
  const users = useLoad(() => api.GET('/api/users'), [])

  return (
    <div className="card">
      <h3>{t('championship.members')}</h3>
      {members.data?.length === 0 && <p>{t('championship.noMembers')}</p>}
      <ul className="list">
        {members.data?.map((member) => (
          <li key={member.user_id}>
            {member.username} <span className="badge">{t(`championship.roles.${member.role}`)}</span>
          </li>
        ))}
      </ul>
      <ActionForm
        title={t('championship.setMember')}
        submitLabel={t('common.save')}
        onSubmit={async (form) => {
          const { error } = await api.PUT('/api/championships/{championship_id}/members', {
            params: { path },
            body: {
              user_id: Number(form.get('user_id')),
              role: form.get('role') as 'admin' | 'driver',
            },
          })
          if (!error) members.reload()
          return error
        }}
      >
        <label>
          {t('championship.user')}
          <select name="user_id" required defaultValue="">
            <option value="" disabled>
              {t('common.select')}
            </option>
            {users.data?.map((user) => (
              <option key={user.id} value={user.id}>
                {user.username}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('championship.role')}
          <select name="role" defaultValue="driver">
            <option value="driver">{t('championship.roles.driver')}</option>
            <option value="admin">{t('championship.roles.admin')}</option>
          </select>
        </label>
      </ActionForm>
    </div>
  )
}
