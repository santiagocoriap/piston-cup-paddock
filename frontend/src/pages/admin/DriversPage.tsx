import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { Combobox } from '../../components/Combobox'
import { Dialog } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { Icon } from '../../components/Icon'
import { Loading } from '../../components/Layout'
import { errorMessage } from '../../lib/errors'
import { initials } from '../../lib/initials'
import { useLoad } from '../../lib/useLoad'
import { Breadcrumbs } from '../../components/Breadcrumbs'
import { DangerMenu } from '../../components/DangerMenu'

type Driver = components['schemas']['DriverOut']
type Account = components['schemas']['UserOut']

export function DriversPage() {
  const { t } = useTranslation()
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  const users = useLoad(() => api.GET('/api/users'), [])
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const [linking, setLinking] = useState<number | null>(null)
  const [merging, setMerging] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const addButton = (
    <button type="button" onClick={() => setAdding(true)}>
      <Icon name="plus" small />
      {t('drivers.newDriver')}
    </button>
  )

  const list = drivers.data ?? []
  const needle = query.trim().toLowerCase()
  const shown = needle
    ? list.filter((d) => [d.display_name, d.steam_guid ?? '', d.username ?? ''].some((text) => text.toLowerCase().includes(needle)))
    : list
  const linkTarget = list.find((d) => d.id === linking)
  const mergeTarget = list.find((d) => d.id === merging)

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.drivers') }]} />
      <header className="page-head">
        <div>
          <h1>{t('drivers.title')}</h1>
          <p className="muted">{t('drivers.help')}</p>
        </div>
        {list.length > 0 && <div className="page-actions">{addButton}</div>}
      </header>
      {notice && (
        <p role="status" className="notice-ok">
          <Icon name="check" small />
          {notice}
        </p>
      )}
      {!drivers.data ? (
        <Loading failed={drivers.failed} />
      ) : list.length === 0 ? (
        <EmptyState icon="users" title={t('drivers.empty')} text={t('drivers.emptyText')}>
          {addButton}
        </EmptyState>
      ) : (
        <>
          <div className="table-tools">
            <label className="search-field">
              <span className="sr-only">{t('drivers.search')}</span>
              <Icon name="search" small />
              <input type="search" value={query} placeholder={t('drivers.searchPlaceholder')} onChange={(e) => setQuery(e.target.value)} />
            </label>
            <span className="muted">{t('drivers.count', { count: shown.length })}</span>
          </div>
          {shown.length === 0 ? (
            <p className="muted">{t('drivers.noMatch', { query: query.trim() })}</p>
          ) : (
            <div className="table-wrap">
              <table className="driver-table">
                <thead>
                  <tr>
                    <th scope="col">{t('drivers.displayName')}</th>
                    <th scope="col">Steam GUID</th>
                    <th scope="col">{t('drivers.account')}</th>
                    <th scope="col" className="num">
                      {t('drivers.careerPoints')}
                    </th>
                    <th scope="col">
                      <span className="sr-only">{t('drivers.actionsColumn')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((driver) => (
                    <tr key={driver.id}>
                      <td>
                        <span className="driver-cell">
                          <span className="avatar" aria-hidden="true">
                            {initials(driver.display_name)}
                          </span>
                          <span className="driver-names">
                            <Link to={`/drivers/${driver.id}`}>{driver.display_name}</Link>
                            {/* A phone hides the account column, so the account shows here. A wide screen hides this line. */}
                            <span className="driver-phone-account muted">
                              {driver.username ? `@${driver.username}` : t('drivers.noAccount')}
                            </span>
                          </span>
                        </span>
                      </td>
                      <td className="mono">{driver.steam_guid ?? '—'}</td>
                      <td>
                        {driver.username ? (
                          <span className="badge account-badge">@{driver.username}</span>
                        ) : (
                          <span className="badge no-account">{t('drivers.noAccount')}</span>
                        )}
                      </td>
                      <td className="num">{driver.career_points}</td>
                      <td className="row-actions">
                        <DangerMenu
                          target={{ kind: 'driver', id: driver.id, name: driver.display_name }}
                          onDeleted={drivers.reload}
                          label={t('drivers.actions', { name: driver.display_name })}
                          items={[
                            { label: t('drivers.linkAccount'), onSelect: () => setLinking(driver.id) },
                            ...(list.length > 1 ? [{ label: t('drivers.mergeWith'), onSelect: () => setMerging(driver.id) }] : []),
                          ]}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <Dialog open={adding} title={t('drivers.newDriver')} onClose={() => setAdding(false)}>
        <ActionForm
          title={t('drivers.newDriver')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const guid = String(form.get('steam_guid') ?? '').trim()
            const { error } = await api.POST('/api/drivers', {
              body: { display_name: String(form.get('display_name')), steam_guid: guid || null },
            })
            if (!error) {
              setAdding(false)
              drivers.reload()
            }
            return error
          }}
        >
          <label>
            {t('drivers.displayName')}
            <input name="display_name" required maxLength={100} />
          </label>
          <label>
            {t('drivers.steamGuid')}
            <input name="steam_guid" inputMode="numeric" pattern="\d{17}" />
          </label>
        </ActionForm>
      </Dialog>

      <Dialog
        open={linkTarget !== undefined}
        title={linkTarget ? t('drivers.linkTitle', { name: linkTarget.display_name }) : ''}
        onClose={() => setLinking(null)}
      >
        {linkTarget && (
          <LinkAccount key={linkTarget.id} driver={linkTarget} drivers={list} users={users.data ?? []} onSaved={drivers.reload} />
        )}
      </Dialog>

      <Dialog open={mergeTarget !== undefined} title={t('drivers.merge')} onClose={() => setMerging(null)}>
        {mergeTarget && (
          <MergeProfiles
            key={mergeTarget.id}
            first={mergeTarget}
            drivers={list}
            onMerged={(message) => {
              setMerging(null)
              setNotice(message)
              drivers.reload()
            }}
          />
        )}
      </Dialog>
    </section>
  )
}

function LinkAccount({ driver, drivers, users, onSaved }: { driver: Driver; drivers: Driver[]; users: Account[]; onSaved: () => void }) {
  const { t } = useTranslation()
  const current = driver.user_id === null ? '' : String(driver.user_id)
  const [value, setValue] = useState(current)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const owners = new Map(drivers.filter((d) => d.user_id !== null && d.id !== driver.id).map((d) => [d.user_id, d.display_name]))
  const options = [
    { value: '', label: t('drivers.noAccount') },
    ...users.map((user) => {
      const owner = owners.get(user.id)
      return { value: String(user.id), label: user.username, hint: owner ? t('drivers.takenBy', { name: owner }) : undefined, disabled: Boolean(owner) }
    }),
  ]
  return (
    <form
      className="modal-body"
      aria-label={t('drivers.linkTitle', { name: driver.display_name })}
      onSubmit={async (event) => {
        event.preventDefault()
        setBusy(true)
        setError(null)
        setSaved(false)
        const { error: apiError } = await api.POST('/api/drivers/{driver_id}/link', {
          params: { path: { driver_id: driver.id } },
          body: { user_id: value ? Number(value) : null },
        })
        setBusy(false)
        if (apiError) return setError(errorMessage(t, apiError))
        setSaved(true)
        onSaved()
      }}
    >
      <h3>{t('drivers.linkTitle', { name: driver.display_name })}</h3>
      <p className="muted">{t('drivers.linkHelp')}</p>
      <Combobox
        label={t('drivers.accountSearch')}
        options={options}
        value={value}
        onChange={(next) => {
          setValue(next)
          setSaved(false)
        }}
        emptyText={t('drivers.noOptions')}
      />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="notice-ok">
          <Icon name="check" small />
          {t('drivers.saved')}
        </p>
      )}
      <div className="modal-actions">
        <button type="submit" disabled={busy || value === current}>
          {t('common.save')}
        </button>
      </div>
    </form>
  )
}

/** Merge two profiles. The two sides show what each profile has, and the problems block the merge. */
function MergeProfiles({ first, drivers, onMerged }: { first: Driver; drivers: Driver[]; onMerged: (message: string) => void }) {
  const { t } = useTranslation()
  const [oldId, setOldId] = useState(first.id)
  const [keptId, setKeptId] = useState('')
  const [reason, setReason] = useState('')
  const [understood, setUnderstood] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const old = drivers.find((d) => d.id === oldId)!
  const kept = drivers.find((d) => String(d.id) === keptId)
  const oldProfile = useLoad(() => api.GET('/api/drivers/{driver_id}/profile', { params: { path: { driver_id: oldId } } }), [oldId])
  const keptProfile = useLoad(
    () =>
      kept
        ? api.GET('/api/drivers/{driver_id}/profile', { params: { path: { driver_id: kept.id } } })
        : Promise.resolve({ data: undefined }),
    [kept?.id],
  )

  // The same checks as the server, so the button stays off with a reason on screen.
  const problems: string[] = []
  if (kept) {
    if (old.user_id !== null && kept.user_id !== null) problems.push('both_have_accounts')
    if (old.steam_guid && kept.steam_guid && old.steam_guid !== kept.steam_guid) problems.push('different_steam_ids')
    const oldSeasons = new Set(oldProfile.data?.seasons.map((s) => s.season_id))
    if (keptProfile.data?.seasons.some((s) => oldSeasons.has(s.season_id))) problems.push('both_in_season')
  }
  const ready = kept !== undefined && problems.length === 0 && reason.trim() !== '' && understood && !busy

  const options = drivers
    .filter((d) => d.id !== oldId)
    .map((d) => ({ value: String(d.id), label: d.display_name, hint: d.username ? `@${d.username}` : undefined }))

  return (
    <form
      className="modal-body"
      aria-label={t('drivers.merge')}
      onSubmit={async (event) => {
        event.preventDefault()
        if (!ready || !kept) return
        setBusy(true)
        setError(null)
        const { error: apiError } = await api.POST('/api/drivers/{driver_id}/merge', {
          params: { path: { driver_id: old.id } },
          body: { into_id: kept.id, reason: reason.trim() },
        })
        setBusy(false)
        if (apiError) return setError(errorMessage(t, apiError))
        onMerged(t('drivers.merged', { old: old.display_name, kept: kept.display_name }))
      }}
    >
      <h3>{t('drivers.merge')}</h3>
      <p className="muted">{t('drivers.mergeHelp')}</p>
      <Combobox label={t('drivers.mergeInto')} options={options} value={keptId} onChange={setKeptId} emptyText={t('drivers.noMatch', { query: '' })} />
      <div className="merge-compare">
        <ProfileSide tone="deleted" label={t('drivers.deleted')} driver={old} profile={oldProfile.data} />
        <button
          type="button"
          className="secondary icon-button merge-swap"
          aria-label={t('drivers.swap')}
          title={t('drivers.swap')}
          disabled={!kept}
          onClick={() => {
            if (!kept) return
            setKeptId(String(old.id))
            setOldId(kept.id)
            setUnderstood(false)
          }}
        >
          <Icon name="swap" small />
        </button>
        {kept ? (
          <ProfileSide tone="kept" label={t('drivers.kept')} driver={kept} profile={keptProfile.data} />
        ) : (
          <div className="merge-side merge-empty muted">{t('drivers.pickKept')}</div>
        )}
      </div>
      {problems.map((code) => (
        <p key={code} role="alert" className="error">
          {t(`errors.${code}`)}
        </p>
      ))}
      <label>
        {t('drivers.mergeReason')}
        <input value={reason} required maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
        {t('drivers.mergeConfirm', { name: old.display_name })}
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="modal-actions">
        <button type="submit" className="danger" disabled={!ready}>
          {t('drivers.mergeButton')}
        </button>
      </div>
    </form>
  )
}

type Profile = components['schemas']['ProfileOut']

function ProfileSide({ tone, label, driver, profile }: { tone: 'deleted' | 'kept'; label: string; driver: Driver; profile: Profile | undefined }) {
  const { t } = useTranslation()
  return (
    <section className={`merge-side merge-${tone}`} aria-label={`${label}: ${driver.display_name}`}>
      <p className="merge-tag">{label}</p>
      <p className="merge-name">{driver.display_name}</p>
      <dl>
        <dt>{t('drivers.account')}</dt>
        <dd>{driver.username ? `@${driver.username}` : t('drivers.noAccount')}</dd>
        <dt>Steam GUID</dt>
        <dd className="mono">{driver.steam_guid ?? '—'}</dd>
        <dt>{t('drivers.careerPoints')}</dt>
        <dd>{driver.career_points}</dd>
        <dt>{t('drivers.seasons')}</dt>
        <dd>{profile ? profile.seasons.map((s) => `${s.championship_name} ${s.season_name}`).join(', ') || t('drivers.none') : '…'}</dd>
        <dt>{t('drivers.records')}</dt>
        <dd>{profile ? profile.records.length : '…'}</dd>
      </dl>
    </section>
  )
}
