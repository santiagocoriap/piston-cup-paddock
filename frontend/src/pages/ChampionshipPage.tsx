import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import { ActionForm } from '../components/ActionForm'
import { Loading } from '../components/Layout'
import { useLoad } from '../lib/useLoad'
import { useAdminView } from '../session'
import { CollectorsSection } from './CollectorsSection'

export function ChampionshipPage() {
  const { t } = useTranslation()
  const championshipId = Number(useParams().championshipId)
  const path = { championship_id: championshipId }
  const championship = useLoad(
    () => api.GET('/api/championships/{championship_id}', { params: { path } }),
    [championshipId],
  )

  const data = championship.data
  const adminView = useAdminView(data?.can_manage ?? false)
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

      {adminView && (
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
          <Roles championshipId={championshipId} />
          <CollectorsSection championshipId={championshipId} />
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
  const roles = useLoad(
    () => api.GET('/api/championships/{championship_id}/roles', { params: { path } }),
    [championshipId],
  )

  return (
    <div className="card">
      <h3>{t('championship.members')}</h3>
      {members.data?.length === 0 && <p>{t('championship.noMembers')}</p>}
      <ul className="list">
        {members.data?.map((member) => (
          <li key={member.user_id}>
            {member.username}{' '}
            <span className="badge">{member.custom_role_name ?? t(`championship.roles.${member.role}`)}</span>
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
              role: form.get('role') as 'admin' | 'driver' | 'steward' | 'custom',
              custom_role_id: form.get('role') === 'custom' ? Number(form.get('custom_role_id')) || null : null,
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
            <option value="steward">{t('championship.roles.steward')}</option>
            <option value="custom">{t('championship.roles.custom')}</option>
            <option value="admin">{t('championship.roles.admin')}</option>
          </select>
        </label>
        <label>
          {t('championship.customRole')}
          <select name="custom_role_id" defaultValue="">
            <option value="">—</option>
            {roles.data?.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
        </label>
      </ActionForm>
    </div>
  )
}

const CAPABILITIES = ['results', 'penalties', 'restarts', 'reports', 'records'] as const
type Capability = (typeof CAPABILITIES)[number]

/** Custom roles of this championship. A role works only in this championship. */
function Roles({ championshipId }: { championshipId: number }) {
  const { t } = useTranslation()
  const path = { championship_id: championshipId }
  const roles = useLoad(
    () => api.GET('/api/championships/{championship_id}/roles', { params: { path } }),
    [championshipId],
  )
  const chosen = (form: FormData): Capability[] => CAPABILITIES.filter((c) => form.get(c) === 'on')

  return (
    <div className="card">
      <h3>{t('championship.customRoles')}</h3>
      <p className="muted">{t('championship.rolesHelp')}</p>
      {roles.data?.length === 0 && <p>{t('championship.noRoles')}</p>}
      {roles.data?.map((role) => (
        <ActionForm
          key={role.id}
          title={t('championship.editRole', { name: role.name, count: role.members })}
          submitLabel={t('common.save')}
          onSubmit={async (form) => {
            const { error } = await api.PUT('/api/roles/{role_id}', {
              params: { path: { role_id: role.id } },
              body: { name: String(form.get('name')), capabilities: chosen(form) },
            })
            if (!error) roles.reload()
            return error
          }}
        >
          <RoleFields name={role.name} capabilities={role.capabilities} />
        </ActionForm>
      ))}
      <ActionForm
        title={t('championship.newRole')}
        submitLabel={t('championship.createRole')}
        onSubmit={async (form) => {
          const { error } = await api.POST('/api/championships/{championship_id}/roles', {
            params: { path },
            body: { name: String(form.get('name')), capabilities: chosen(form) },
          })
          if (!error) roles.reload()
          return error
        }}
      >
        <RoleFields name="" capabilities={[]} />
      </ActionForm>
    </div>
  )
}

function RoleFields({ name, capabilities }: { name: string; capabilities: string[] }) {
  const { t } = useTranslation()
  return (
    <>
      <label>
        {t('championship.roleName')}
        <input name="name" defaultValue={name} required maxLength={60} />
      </label>
      <fieldset>
        <legend>{t('championship.capabilities')}</legend>
        {CAPABILITIES.map((capability) => (
          <label key={capability} className="check">
            <input type="checkbox" name={capability} defaultChecked={capabilities.includes(capability)} />
            {t(`championship.capability.${capability}`)}
          </label>
        ))}
      </fieldset>
    </>
  )
}
