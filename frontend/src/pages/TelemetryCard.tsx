import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { SettingsRow } from '../components/SettingsRow'

type Level = 'none' | 'laps' | 'full'

/** The laps of the driver from the Paddock script, and who sees them. */
export function TelemetryCard() {
  const { t, i18n } = useTranslation()
  const status = useLoad(() => api.GET('/api/me/telemetry'), [])
  const [message, setMessage] = useState<{ kind: 'error' | 'status'; text: string } | null>(null)
  const data = status.data
  if (!data || !data.has_driver || !data.sharing) return null

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const { error } = await api.PUT('/api/me/telemetry/sharing', {
      body: {
        teammates: form.get('teammates') as Level,
        drivers: form.get('drivers') as Level,
        admins: form.get('admins') as Level,
      },
    })
    setMessage(error ? { kind: 'error', text: errorMessage(t, error) } : { kind: 'status', text: t('telemetry.saved') })
  }

  const levels = () => (
    <>
      <option value="none">{t('telemetry.levels.none')}</option>
      <option value="laps">{t('telemetry.levels.laps')}</option>
      <option value="full">{t('telemetry.levels.full')}</option>
    </>
  )

  return (
    <SettingsRow id="telemetry" title={t('telemetry.title')} help={t('telemetry.help')}>
      <div className="key-status">
        <span className={data.laps ? 'key-dot on' : 'key-dot'} aria-hidden="true" />
        <p>
          <b>{t('telemetry.laps', { count: data.laps })}</b>
          {data.last_lap_at && (
            <span className="muted">{t('telemetry.lastLap', { date: formatDateTime(data.last_lap_at, i18n.language) })}</span>
          )}
        </p>
      </div>
      <form className="sharing-form" onSubmit={save} aria-label={t('telemetry.sharing')}>
        <h3>{t('telemetry.sharing')}</h3>
        <label>
          {t('telemetry.teammates')}
          <select name="teammates" defaultValue={data.sharing.teammates}>
            {levels()}
          </select>
        </label>
        <label>
          {t('telemetry.drivers')}
          <select name="drivers" defaultValue={data.sharing.drivers}>
            {levels()}
          </select>
        </label>
        <label>
          {t('telemetry.admins')}
          <select name="admins" defaultValue={data.sharing.admins}>
            {levels()}
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
