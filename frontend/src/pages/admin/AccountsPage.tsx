import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { Loading } from '../../components/Layout'
import { errorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

type LinkOut = components['schemas']['LinkOut']

/** Admins make accounts and send one-time links. The app sends no email. */
export function AccountsPage() {
  const { t, i18n } = useTranslation()
  const accounts = useLoad(() => api.GET('/api/accounts'), [])
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  const championships = useLoad(() => api.GET('/api/championships'), [])
  const [link, setLink] = useState<LinkOut | null>(null)
  const [error, setError] = useState<string | null>(null)

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
  return (
    <section>
      <h1>{t('accounts.title')}</h1>
      <p className="muted">{t('accounts.help')}</p>
      {link && <LinkBox link={link} />}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('accounts.username')}</th>
              <th scope="col">{t('accounts.driver')}</th>
              <th scope="col">{t('accounts.championships')}</th>
              <th scope="col">{t('accounts.status')}</th>
              <th scope="col">{t('accounts.lastLogin')}</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {accounts.data.map((account) => (
              <tr key={account.id}>
                <td>{account.username}</td>
                <td>{account.driver_name ?? '—'}</td>
                <td className="muted">{account.championships.join(', ') || '—'}</td>
                <td>
                  {account.has_password ? t('accounts.active') : t('accounts.pending')}
                  {account.open_link && <span className="badge">{t('accounts.openLink')}</span>}
                </td>
                <td className="muted">
                  {account.last_login ? formatDateTime(account.last_login, i18n.language) : t('accounts.never')}
                </td>
                <td>
                  <button type="button" className="secondary small" onClick={() => newLink(account.id)}>
                    {t('accounts.newLink')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="forms">
        <ActionForm
          title={t('accounts.new')}
          submitLabel={t('accounts.create')}
          onSubmit={async (form) => {
            const driver = form.get('driver_id')
            const championship = form.get('championship_id')
            const { data, error } = await api.POST('/api/accounts', {
              body: {
                username: String(form.get('username') ?? '').trim(),
                driver_id: driver ? Number(driver) : null,
                championship_id: championship ? Number(championship) : null,
                role: championship ? (form.get('role') as 'driver' | 'admin') : null,
              },
            })
            if (data) {
              setLink(data)
              accounts.reload()
              drivers.reload()
            }
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
              {drivers.data
                ?.filter((driver) => driver.user_id === null)
                .map((driver) => (
                  <option key={driver.id} value={driver.id}>
                    {driver.display_name}
                  </option>
                ))}
            </select>
          </label>
          <div className="field-row">
            <label>
              {t('accounts.championship')}
              <select name="championship_id" defaultValue="">
                <option value="">{t('accounts.noChampionship')}</option>
                {championships.data
                  ?.filter((c) => c.can_manage)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              {t('accounts.role')}
              <select name="role" defaultValue="driver">
                <option value="driver">{t('championship.roles.driver')}</option>
                <option value="admin">{t('championship.roles.admin')}</option>
              </select>
            </label>
          </div>
        </ActionForm>
      </div>
    </section>
  )
}

function LinkBox({ link }: { link: LinkOut }) {
  const { t, i18n } = useTranslation()
  const [copied, setCopied] = useState(false)
  const url = `${window.location.origin}${link.link_path}`

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false) // The browser blocks the clipboard. The admin copies the text by hand.
    }
  }

  return (
    <div className="card link-box" role="region" aria-label={t('accounts.link', { name: link.account.username })}>
      <h3>{t('accounts.link', { name: link.account.username })}</h3>
      <input readOnly value={url} onFocus={(event) => event.target.select()} aria-label={t('accounts.link', { name: link.account.username })} />
      <p className="muted">{t('accounts.expires', { date: formatDateTime(link.expires_at, i18n.language) })}</p>
      <button type="button" onClick={copy}>
        {t('accounts.copy')}
      </button>
      {copied && (
        <p role="status" className="success">
          {t('accounts.copied')}
        </p>
      )}
    </div>
  )
}
