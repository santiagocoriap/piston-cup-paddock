import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Icon } from '../components/Icon'
import { SettingsRow } from '../components/SettingsRow'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

/** The MCP address for Claude, and the clients that the user allowed, with a button to remove
 * each one. */
export function ConnectionsCard() {
  const { t, i18n } = useTranslation()
  const load = useLoad(() => api.GET('/api/me/connections'), [])
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const url = `${window.location.origin}/mcp`

  async function copy() {
    await navigator.clipboard?.writeText(url)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  async function remove(id: number, name: string) {
    if (!window.confirm(t('connections.confirmRemove', { name }))) return
    setError(null)
    const { error: failed } = await api.DELETE('/api/me/connections/{application_id}', {
      params: { path: { application_id: id } },
    })
    if (failed) setError(errorMessage(t, failed))
    else load.reload()
  }

  return (
    <SettingsRow id="connections" title={t('connections.title')} help={t('connections.help')}>
      <label>
        {t('connections.address')}
        <span className="copy-field">
          <input readOnly value={url} onFocus={(e) => e.target.select()} />
          <button type="button" className="secondary" onClick={copy}>
            <Icon name={copied ? 'check' : 'copy'} small />
            {copied ? t('calendar.copied') : t('calendar.copy')}
          </button>
        </span>
      </label>
      <ol className="connections-steps muted">
        <li>{t('connections.step1')}</li>
        <li>{t('connections.step2')}</li>
        <li>{t('connections.step3')}</li>
      </ol>
      {load.data && load.data.length === 0 && <p className="muted">{t('connections.none')}</p>}
      {load.data && load.data.length > 0 && (
        <ul className="connections-list">
          {load.data.map((item) => (
            <li key={item.application_id}>
              <span>
                <b>{item.name}</b>
                <small className="muted">
                  {t('connections.since', { date: formatDateTime(item.connected_at, i18n.language) })} ·{' '}
                  {t('connections.last', { date: formatDateTime(item.last_access_at, i18n.language) })}
                </small>
              </span>
              {!item.active && <span className="badge">{t('connections.expired')}</span>}
              <button type="button" className="secondary small" onClick={() => remove(item.application_id, item.name)}>
                {t('connections.remove')}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </SettingsRow>
  )
}
