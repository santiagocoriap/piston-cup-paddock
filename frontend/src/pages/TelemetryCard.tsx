import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { SettingsRow } from '../components/SettingsRow'

type Level = 'none' | 'laps' | 'full'

/** The driver collector key, its status, and who sees the telemetry of the driver. */
export function TelemetryCard() {
  const { t, i18n } = useTranslation()
  const status = useLoad(() => api.GET('/api/me/telemetry'), [])
  const [key, setKey] = useState<string | null>(null)
  const [message, setMessage] = useState<{ kind: 'error' | 'status'; text: string } | null>(null)
  const data = status.data
  if (!data || !data.has_driver || !data.sharing) return null

  async function makeKey() {
    if (data?.has_key && !window.confirm(t('telemetry.replaceKey'))) return
    const { data: created, error } = await api.POST('/api/me/telemetry/key')
    if (created) {
      setKey(created.key)
      status.reload()
    } else setMessage({ kind: 'error', text: errorMessage(t, error) })
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const { error } = await api.PUT('/api/me/telemetry/sharing', {
      body: {
        teammates: form.get('teammates') as Level,
        drivers: form.get('drivers') as 'none' | 'laps',
        admins: form.get('admins') as Level,
      },
    })
    setMessage(error ? { kind: 'error', text: errorMessage(t, error) } : { kind: 'status', text: t('telemetry.saved') })
  }

  const levels = (allowFull: boolean) => (
    <>
      <option value="none">{t('telemetry.levels.none')}</option>
      <option value="laps">{t('telemetry.levels.laps')}</option>
      {allowFull && <option value="full">{t('telemetry.levels.full')}</option>}
    </>
  )

  return (
    <SettingsRow id="telemetry" title={t('telemetry.title')} help={t('telemetry.help')}>
      <div className="key-status">
        <span className={data.last_seen_at ? 'key-dot on' : data.has_key ? 'key-dot waiting' : 'key-dot'} aria-hidden="true" />
        <p>
          <b>
            {data.has_key
              ? data.last_seen_at
                ? t('telemetry.lastSeen', { date: formatDateTime(data.last_seen_at, i18n.language) })
                : t('telemetry.neverSeen')
              : t('telemetry.noKey')}
          </b>
          <span className="muted">{t('telemetry.laps', { count: data.laps })}</span>
        </p>
        <button type="button" className={data.has_key ? 'secondary' : undefined} onClick={makeKey}>
          {data.has_key ? t('telemetry.newKey') : t('telemetry.makeKey')}
        </button>
      </div>
      {key && (
        <div className="link-box" role="status">
          <p>{t('telemetry.keyOnce')}</p>
          <input readOnly value={key} onFocus={(e) => e.target.select()} aria-label={t('telemetry.key')} />
        </div>
      )}
      <form className="sharing-form" onSubmit={save} aria-label={t('telemetry.sharing')}>
        <h3>{t('telemetry.sharing')}</h3>
        <label>
          {t('telemetry.teammates')}
          <select name="teammates" defaultValue={data.sharing.teammates}>
            {levels(true)}
          </select>
        </label>
        <label>
          {t('telemetry.drivers')}
          <select name="drivers" defaultValue={data.sharing.drivers}>
            {levels(false)}
          </select>
        </label>
        <label>
          {t('telemetry.admins')}
          <select name="admins" defaultValue={data.sharing.admins}>
            {levels(true)}
          </select>
        </label>
        <p className="muted">{t('telemetry.protected')}</p>
        {message && (
          <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
            {message.text}
          </p>
        )}
        <div className="settings-actions">
          <button type="submit">{t('common.save')}</button>
        </div>
      </form>
    </SettingsRow>
  )
}
