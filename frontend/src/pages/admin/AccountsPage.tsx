import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { Dialog } from '../../components/Dialog'
import { Icon } from '../../components/Icon'
import { Loading } from '../../components/Layout'
import { errorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { initials } from '../../lib/initials'
import { useLoad } from '../../lib/useLoad'
import { Breadcrumbs } from '../../components/Breadcrumbs'
import { DangerMenu } from '../../components/DangerMenu'

type LinkOut = components['schemas']['LinkOut']
type Driver = components['schemas']['DriverOut']
type Championship = components['schemas']['ChampionshipOut']

/** Admins make accounts and send one-time links. The app sends no email. */
export function AccountsPage() {
  const { t, i18n } = useTranslation()
  const accounts = useLoad(() => api.GET('/api/accounts'), [])
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  const championships = useLoad(() => api.GET('/api/championships'), [])
  const [creating, setCreating] = useState(false)
  const [formKey, setFormKey] = useState(0)
  const [link, setLink] = useState<LinkOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  async function newLink(userId: number) {
    setError(null)
    const { data, error } = await api.POST('/api/accounts/{user_id}/link', {
      params: { path: { user_id: userId } },
    })
    if (error || !data) setError(errorMessage(t, error))
    else {
      setLink(data)
      accounts.reload()
    }
  }

  if (!accounts.data) return <Loading failed={accounts.failed} />
  const needle = query.trim().toLowerCase()
  const shown = needle
    ? accounts.data.filter((a) =>
        [a.username, a.driver_name ?? '', ...a.championships].some((text) => text.toLowerCase().includes(needle)),
      )
    : accounts.data

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.accounts') }]} />
      <header className="page-head">
        <div>
          <h1>{t('accounts.title')}</h1>
          <p className="muted">{t('accounts.help')}</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            onClick={() => {
              setFormKey((key) => key + 1)
              setCreating(true)
            }}
          >
            <Icon name="plus" small />
            {t('accounts.new')}
          </button>
        </div>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <div className="table-tools">
        <label className="search-field">
          <span className="sr-only">{t('accounts.search')}</span>
          <Icon name="search" small />
          <input type="search" value={query} placeholder={t('accounts.searchPlaceholder')} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <span className="muted">{t('accounts.count', { count: shown.length })}</span>
      </div>

      {shown.length === 0 ? (
        <p className="muted">{t('accounts.noMatch', { query: query.trim() })}</p>
      ) : (
        <div className="table-wrap">
          <table className="account-table">
            <thead>
              <tr>
                <th scope="col">{t('accounts.username')}</th>
                <th scope="col">{t('accounts.driver')}</th>
                <th scope="col">{t('accounts.championships')}</th>
                <th scope="col">{t('accounts.status')}</th>
                <th scope="col">{t('accounts.lastLogin')}</th>
                <th scope="col">
                  <span className="sr-only">{t('accounts.actionsColumn')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((account) => (
                <tr key={account.id}>
                  <td>
                    <span className="driver-cell">
                      <span className="avatar" aria-hidden="true">
                        {initials(account.username)}
                      </span>
                      <span className="driver-names">
                        {account.username}
                        {/* A phone hides the status column, so the status shows here. A wide screen hides this line. */}
                        <span className="driver-phone-account muted">
                          {account.has_password ? t('accounts.active') : t('accounts.pendingShort')}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className={account.driver_name ? undefined : 'muted'}>{account.driver_name ?? '—'}</td>
                  <td>
                    {account.championships.length === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      <span className="chip-list">
                        {account.championships.map((name) => (
                          <span key={name} className="badge chip">
                            {name}
                          </span>
                        ))}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className="status-cell">
                      {account.has_password ? (
                        <span className="badge status-badge accepted">{t('accounts.active')}</span>
                      ) : (
                        <span className="badge status-badge pending">{t('accounts.pendingShort')}</span>
                      )}
                      {account.open_link && <span className="muted status-note">{t('accounts.openLink')}</span>}
                    </span>
                  </td>
                  <td className="muted">
                    {account.last_login ? formatDateTime(account.last_login, i18n.language) : t('accounts.never')}
                  </td>
                  <td className="row-actions">
                    <DangerMenu
                      target={{ kind: 'user', id: account.id, name: account.username }}
                      onDeleted={accounts.reload}
                      label={t('accounts.actions', { name: account.username })}
                      items={[
                        {
                          label: account.has_password ? t('accounts.resetLink') : t('accounts.inviteLink'),
                          onSelect: () => newLink(account.id),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={creating} title={t('accounts.new')} onClose={() => setCreating(false)}>
        <NewAccountForm
          key={formKey}
          drivers={drivers.data ?? []}
          championships={championships.data ?? []}
          onCreated={(data) => {
            setCreating(false)
            setLink(data)
            accounts.reload()
            drivers.reload()
          }}
        />
      </Dialog>

      <Dialog open={link !== null} title={t('accounts.linkTitle')} onClose={() => setLink(null)}>
        {link && <LinkBox link={link} onDone={() => setLink(null)} />}
      </Dialog>
    </section>
  )
}

function NewAccountForm({
  drivers,
  championships,
  onCreated,
}: {
  drivers: Driver[]
  championships: Championship[]
  onCreated: (link: LinkOut) => void
}) {
  const { t } = useTranslation()
  const [championship, setChampionship] = useState('')
  const roleLabel = useId()
  const roleHint = useId()
  return (
    <ActionForm
      title={t('accounts.new')}
      submitLabel={t('accounts.create')}
      onSubmit={async (form) => {
        const driver = form.get('driver_id')
        const { data, error } = await api.POST('/api/accounts', {
          body: {
            username: String(form.get('username') ?? '').trim(),
            driver_id: driver ? Number(driver) : null,
            championship_id: championship ? Number(championship) : null,
            role: championship ? (form.get('role') as 'driver' | 'admin') : null,
          },
        })
        if (data) onCreated(data)
        return error
      }}
    >
      <label>
        {t('accounts.username')}
        <input name="username" required maxLength={150} pattern="[\w.@+\-]+" autoComplete="off" />
      </label>
      <label>
        {t('accounts.driver')}
        <select name="driver_id" defaultValue="">
          <option value="">{t('accounts.noDriver')}</option>
          {drivers
            .filter((driver) => driver.user_id === null)
            .map((driver) => (
              <option key={driver.id} value={driver.id}>
                {driver.display_name}
              </option>
            ))}
        </select>
      </label>
      <label>
        {t('accounts.championship')}
        <select name="championship_id" value={championship} onChange={(e) => setChampionship(e.target.value)}>
          <option value="">{t('accounts.noChampionship')}</option>
          {championships
            .filter((c) => c.can_manage)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        <span id={roleLabel}>{t('accounts.role')}</span>
        <select
          name="role"
          defaultValue="driver"
          disabled={!championship}
          aria-labelledby={roleLabel}
          aria-describedby={championship ? undefined : roleHint}
        >
          <option value="driver">{t('championship.roles.driver')}</option>
          <option value="admin">{t('championship.roles.admin')}</option>
        </select>
        {!championship && (
          <span id={roleHint} className="field-hint">
            {t('accounts.roleHint')}
          </span>
        )}
      </label>
    </ActionForm>
  )
}

function LinkBox({ link, onDone }: { link: LinkOut; onDone: () => void }) {
  const { t, i18n } = useTranslation()
  const [copied, setCopied] = useState(false)
  const url = `${window.location.origin}${link.link_path}`
  const name = t('accounts.link', { name: link.account.username })

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false) // The browser blocks the clipboard. The admin copies the text by hand.
    }
  }

  return (
    <div className="modal-body link-box" role="region" aria-label={name}>
      <h3>{name}</h3>
      <p className="muted">{t('accounts.linkHelp')}</p>
      <input className="mono" readOnly value={url} onFocus={(event) => event.target.select()} aria-label={name} />
      <p className="muted">
        <Icon name="clock" small /> {t('accounts.expires', { date: formatDateTime(link.expires_at, i18n.language) })}
      </p>
      {copied && (
        <p role="status" className="notice-ok">
          <Icon name="check" small />
          {t('accounts.copied')}
        </p>
      )}
      <div className="modal-actions">
        <button type="button" className="secondary" onClick={copy}>
          <Icon name={copied ? 'check' : 'copy'} small />
          {t('accounts.copy')}
        </button>
        <button type="button" onClick={onDone}>
          {t('accounts.done')}
        </button>
      </div>
    </div>
  )
}
