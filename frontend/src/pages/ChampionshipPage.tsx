import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { AdminActions } from '../components/AdminActions'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Loading } from '../components/Layout'
import { RowMenu } from '../components/RowMenu'
import { Tabs } from '../components/Tabs'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { panelId, tabId } from '../lib/tabs'
import { useLoad } from '../lib/useLoad'
import { useAdminView } from '../session'
import { CollectorsSection } from './CollectorsSection'
import { DriverScriptCard } from './DriverScriptCard'
import { HealthSection } from './HealthSection'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { Avatar } from '../components/Avatar'

type Detail = components['schemas']['ChampionshipDetail']
type Progress = components['schemas']['LatestSeasonOut']
type Season = Detail['seasons'][number]
type Role = components['schemas']['RoleOut']
type MemberRole = 'admin' | 'driver' | 'steward' | 'custom'

const ADMIN_TABS = ['seasons', 'members', 'roles', 'health', 'collectors'] as const
type AdminTab = (typeof ADMIN_TABS)[number]

export function ChampionshipPage() {
  const { t, i18n } = useTranslation()
  const championshipId = Number(useParams().championshipId)
  const path = { championship_id: championshipId }
  const championship = useLoad(
    () => api.GET('/api/championships/{championship_id}', { params: { path } }),
    [championshipId],
  )
  const [tab, setTab] = useState<AdminTab>('seasons')

  const data = championship.data
  const adminView = useAdminView(data?.can_manage ?? false)
  if (!data) return <Loading failed={championship.failed} />
  const latest = data.latest
  const progress = new Map(data.progress.map((item) => [item.season_id, item]))

  return (
    <section>
      <Breadcrumbs items={[{ label: data.name }]} />
      <header className="season-hero champ-hero">
        <div>
          <p className="eyebrow">{data.league_name}</p>
          <h1 className="season-title">{data.name}</h1>
        </div>
        {latest && (
          <dl className="season-stats">
            <div>
              <dt>{t('championship.current')}</dt>
              <dd className="season-stat-text">
                <Link to={`/seasons/${latest.season_id}`}>{latest.name}</Link>
              </dd>
            </div>
            <div>
              <dt>{t('seasonStats.rounds')}</dt>
              <dd>
                {latest.done}
                <small>/ {latest.total}</small>
              </dd>
            </div>
            <div>
              <dt>{t('seasonStats.leader')}</dt>
              <dd className="season-stat-text">{latest.leader ?? '—'}</dd>
            </div>
            <div>
              <dt>{t('seasonStats.next')}</dt>
              <dd className="season-stat-text">
                {latest.next_round ? (
                  <Link to={`/rounds/${latest.next_round.round_id}`}>
                    {t('season.roundLabel', { number: latest.next_round.number })} · {latest.next_round.track_name}
                    <small>{formatDateTime(latest.next_round.scheduled_at, i18n.language)}</small>
                  </Link>
                ) : (
                  '—'
                )}
              </dd>
            </div>
          </dl>
        )}
      </header>

      <h2>{t('championship.seasons')}</h2>
      {data.seasons.length === 0 && <p className="muted">{t('championship.noSeasons')}</p>}
      <ul className="champ-grid">
        {[...data.seasons].reverse().map((season) => (
          <SeasonCard
            key={season.id}
            season={season}
            progress={progress.get(season.id)}
            latest={season.id === latest?.season_id}
            adminView={adminView}
          />
        ))}
      </ul>

      {adminView && (
        <section className="champ-admin" aria-labelledby="champ-admin">
          <h2 id="champ-admin">
            <Icon name="shield" />
            {t('round.adminTools')}
          </h2>
          <div className="champ-admin-layout">
            <Tabs
              label={t('round.adminTools')}
              idPrefix="champ"
              vertical
              tabs={ADMIN_TABS.map((id) => ({ id, label: t(`championship.adminTabs.${id}`) }))}
              active={tab}
              onChange={(id) => setTab(id as AdminTab)}
            />
            <div
              className="champ-admin-panel"
              role="tabpanel"
              id={panelId('champ', tab)}
              aria-labelledby={tabId('champ', tab)}
            >
              {tab === 'seasons' && <SeasonsTab data={data} onChange={championship.reload} />}
              {tab === 'members' && <Members championshipId={championshipId} />}
              {tab === 'roles' && <Roles championshipId={championshipId} />}
              {tab === 'health' && <HealthSection championshipId={championshipId} />}
              {tab === 'collectors' && (
                <>
                  <CollectorsSection championshipId={championshipId} />
                  <DriverScriptCard championshipId={championshipId} />
                </>
              )}
            </div>
          </div>
        </section>
      )}
    </section>
  )
}

/** A season card: the progress bar, the leader, and the next round. */
function SeasonCard({
  season,
  progress,
  latest,
  adminView,
}: {
  season: Season
  progress?: Progress
  latest: boolean
  adminView: boolean
}) {
  const { t, i18n } = useTranslation()
  const done = progress?.done ?? 0
  const total = progress?.total ?? season.planned_round_count
  const next = progress?.next_round
  return (
    <li className="champ-card">
      <div className="champ-head">
        <span className="champ-icon">
          <Icon name="flag" />
        </span>
        <div>
          <h3>
            <Link to={`/seasons/${season.id}`}>{season.name}</Link>
          </h3>
          <p className="muted">{t('season.plannedRounds', { count: season.planned_round_count })}</p>
        </div>
        {latest && <span className="badge">{t('championship.latest')}</span>}
      </div>
      <div className="season-progress">
        <span>{t('championship.progress', { done, total })}</span>
        <span
          className="season-progress-bar"
          role="progressbar"
          aria-label={t('championship.progress', { done, total })}
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
        >
          <span style={{ width: `${total ? Math.min(100, (done / total) * 100) : 0}%` }} />
        </span>
      </div>
      <dl className="champ-facts">
        <div>
          <dt>{t('seasonStats.leader')}</dt>
          <dd>{progress?.leader ?? '—'}</dd>
        </div>
        <div>
          <dt>{t('seasonStats.next')}</dt>
          <dd>
            {next ? (
              <>
                <Link to={`/rounds/${next.round_id}`}>
                  {t('season.roundLabel', { number: next.number })} · {next.track_name}
                </Link>
                {next.scheduled_at && <small>{formatDateTime(next.scheduled_at, i18n.language)}</small>}
              </>
            ) : (
              '—'
            )}
          </dd>
        </div>
      </dl>
      {adminView && (
        <p className="muted champ-season">
          {t('championship.protestWindow', { count: season.protest_window_minutes })}
        </p>
      )}
      <Link className="small-link" to={`/seasons/${season.id}`}>
        {t('championship.openSeason')}
        <Icon name="arrow" small />
      </Link>
    </li>
  )
}

/** The season settings of the championship, and the button for a new season. */
function SeasonsTab({ data, onChange }: { data: Detail; onChange: () => void }) {
  const { t } = useTranslation()
  const path = { championship_id: data.id }
  return (
    <div className="champ-tab">
      <div className="section-head">
        <h3>{t('championship.adminTabs.seasons')}</h3>
        <AdminActions
          actions={[
            {
              id: 'season',
              label: t('championship.newSeason'),
              content: (close) => (
                <ActionForm
                  title={t('championship.newSeason')}
                  submitLabel={t('common.create')}
                  onDone={close}
                  onSubmit={async (form) => {
                    const { error } = await api.POST('/api/championships/{championship_id}/seasons', {
                      params: { path },
                      body: {
                        name: String(form.get('name')),
                        planned_round_count: Number(form.get('planned_round_count')),
                      },
                    })
                    if (!error) onChange()
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
              ),
            },
          ]}
        />
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={data.provisional_reports}
          onChange={async (e) => {
            await api.PATCH('/api/championships/{championship_id}/settings', {
              params: { path },
              body: { provisional_reports: e.target.checked },
            })
            onChange()
          }}
        />
        {t('championship.provisionalReports')}
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={data.auto_publish_results}
          onChange={async (e) => {
            await api.PATCH('/api/championships/{championship_id}/settings', {
              params: { path },
              body: { auto_publish_results: e.target.checked },
            })
            onChange()
          }}
        />
        {t('championship.autoPublish')}
      </label>
      <label className="setting-number">
        {t('championship.openSlots')}
        <input
          type="number"
          min={0}
          max={40}
          defaultValue={data.open_slots}
          key={data.open_slots}
          onBlur={async (e) => {
            const value = Number(e.target.value)
            if (!Number.isInteger(value) || value < 0 || value > 40 || value === data.open_slots) return
            await api.PATCH('/api/championships/{championship_id}/settings', {
              params: { path },
              body: { open_slots: value },
            })
            onChange()
          }}
        />
        <small className="muted">{t('championship.openSlotsHelp')}</small>
      </label>
    </div>
  )
}

/** "driver", "steward", "admin", or "custom:<id>" for a custom role. One select holds all of them. */
function roleValue(role: string, customId?: number | null): string {
  return role === 'custom' && customId ? `custom:${customId}` : role
}

function roleBody(value: string): { role: MemberRole; custom_role_id: number | null } {
  if (value.startsWith('custom:')) return { role: 'custom', custom_role_id: Number(value.slice(7)) }
  return { role: value as MemberRole, custom_role_id: null }
}

function RoleOptions({ roles }: { roles: Role[] }) {
  const { t } = useTranslation()
  return (
    <>
      <option value="driver">{t('championship.roles.driver')}</option>
      <option value="steward">{t('championship.roles.steward')}</option>
      <option value="admin">{t('championship.roles.admin')}</option>
      {roles.map((role) => (
        <option key={role.id} value={`custom:${role.id}`}>
          {role.name}
        </option>
      ))}
    </>
  )
}

/** The members as a table: a picture, the name, and a role menu that saves on change. */
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
  const [error, setError] = useState<string | null>(null)

  async function save(userId: number, value: string) {
    setError(null)
    const { error } = await api.PUT('/api/championships/{championship_id}/members', {
      params: { path },
      body: { user_id: userId, ...roleBody(value) },
    })
    if (error) setError(errorMessage(t, error))
    members.reload()
    return error
  }

  return (
    <div className="champ-tab">
      <div className="section-head">
        <h3>{t('championship.members')}</h3>
        <AdminActions
          actions={[
            {
              id: 'member',
              label: t('championship.addMember'),
              content: (close) => (
                <ActionForm
                  title={t('championship.addMember')}
                  submitLabel={t('common.save')}
                  onDone={close}
                  onSubmit={(form) => save(Number(form.get('user_id')), String(form.get('role')))}
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
                      <RoleOptions roles={roles.data ?? []} />
                    </select>
                  </label>
                </ActionForm>
              ),
            },
          ]}
        />
      </div>
      {members.data?.length === 0 && <p className="muted">{t('championship.noMembers')}</p>}
      {members.data && members.data.length > 0 && (
        <div className="table-wrap">
          <table className="members-table">
            <thead>
              <tr>
                <th scope="col">{t('championship.user')}</th>
                <th scope="col">{t('championship.role')}</th>
              </tr>
            </thead>
            <tbody>
              {members.data.map((member) => (
                <tr key={member.user_id}>
                  <td>
                    <span className="member-name">
                      <Avatar name={member.username} url={member.avatar_url} />
                      {member.username}
                    </span>
                  </td>
                  <td>
                    <select
                      aria-label={t('championship.roleOf', { name: member.username })}
                      value={roleValue(member.role, member.custom_role_id)}
                      onChange={(event) => save(member.user_id, event.target.value)}
                    >
                      <RoleOptions roles={roles.data ?? []} />
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}

const CAPABILITIES = ['results', 'penalties', 'restarts', 'reports', 'records'] as const
type Capability = (typeof CAPABILITIES)[number]

/** Custom roles as a table: one row for each role, one column for each permission.
 * A checkbox saves the role at once. A role works only in this championship. */
function Roles({ championshipId }: { championshipId: number }) {
  const { t } = useTranslation()
  const path = { championship_id: championshipId }
  const roles = useLoad(
    () => api.GET('/api/championships/{championship_id}/roles', { params: { path } }),
    [championshipId],
  )
  const [renaming, setRenaming] = useState<Role | null>(null)
  const [error, setError] = useState<string | null>(null)
  const chosen = (form: FormData): Capability[] => CAPABILITIES.filter((c) => form.get(c) === 'on')

  async function update(role: Role, name: string, capabilities: string[]) {
    setError(null)
    const { error } = await api.PUT('/api/roles/{role_id}', {
      params: { path: { role_id: role.id } },
      body: { name, capabilities: capabilities as Capability[] },
    })
    if (error) setError(errorMessage(t, error))
    roles.reload()
    return error
  }

  return (
    <div className="champ-tab">
      <div className="section-head">
        <h3>{t('championship.customRoles')}</h3>
        <AdminActions
          actions={[
            {
              id: 'role',
              label: t('championship.newRole'),
              content: (close) => (
                <ActionForm
                  title={t('championship.newRole')}
                  submitLabel={t('championship.createRole')}
                  onDone={close}
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
              ),
            },
          ]}
        />
      </div>
      <p className="muted">{t('championship.rolesHelp')}</p>
      {roles.data?.length === 0 && <p className="muted">{t('championship.noRoles')}</p>}
      {roles.data && roles.data.length > 0 && (
        <div className="table-wrap">
          <table className="roles-table">
            <thead>
              <tr>
                <th scope="col">{t('championship.roleName')}</th>
                {CAPABILITIES.map((capability) => (
                  <th key={capability} scope="col" className="c" title={t(`championship.capability.${capability}`)}>
                    {t(`championship.capabilityShort.${capability}`)}
                  </th>
                ))}
                <th scope="col" className="r">
                  {t('championship.members')}
                </th>
                <th scope="col">
                  <span className="sr-only">{t('roundTools.actions')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {roles.data.map((role) => (
                <tr key={role.id}>
                  <td>
                    <strong>{role.name}</strong>
                  </td>
                  {CAPABILITIES.map((capability) => (
                    <td key={capability} className="c">
                      <input
                        type="checkbox"
                        aria-label={t('championship.roleCapability', {
                          role: role.name,
                          capability: t(`championship.capabilityShort.${capability}`),
                        })}
                        checked={role.capabilities.includes(capability)}
                        onChange={(event) =>
                          update(
                            role,
                            role.name,
                            event.target.checked
                              ? [...role.capabilities, capability]
                              : role.capabilities.filter((c) => c !== capability),
                          )
                        }
                      />
                    </td>
                  ))}
                  <td className="r">{role.members}</td>
                  <td className="row-actions">
                    <RowMenu
                      label={t('championship.roleMenu', { name: role.name })}
                      items={[{ label: t('championship.rename'), onSelect: () => setRenaming(role) }]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <Dialog open={renaming !== null} title={t('championship.rename')} onClose={() => setRenaming(null)}>
        {renaming && (
          <ActionForm
            title={t('championship.rename')}
            submitLabel={t('common.save')}
            onDone={() => setRenaming(null)}
            onSubmit={(form) => update(renaming, String(form.get('name')), renaming.capabilities)}
          >
            <label>
              {t('championship.roleName')}
              <input name="name" defaultValue={renaming.name} required maxLength={60} />
            </label>
          </ActionForm>
        )}
      </Dialog>
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
