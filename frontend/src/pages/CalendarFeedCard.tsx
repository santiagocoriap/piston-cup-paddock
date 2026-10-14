import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useLoad } from '../lib/useLoad'
import { Icon } from '../components/Icon'
import { SettingsRow } from '../components/SettingsRow'

/** The private calendar address of the user, for a phone calendar. */
export function CalendarFeedCard() {
  const { t } = useTranslation()
  const load = useLoad(() => api.GET('/api/me/calendar-feed'), [])
  const [path, setPath] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const current = path ?? load.data?.path
  if (!current) return null
  const url = `${window.location.origin}${current}`

  async function copy() {
    await navigator.clipboard?.writeText(url)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  async function replace() {
    if (!window.confirm(t('calendar.confirmNew'))) return
    const { data } = await api.POST('/api/me/calendar-feed')
    if (data) setPath(data.path)
  }

  return (
    <SettingsRow id="calendar-feed" title={t('calendar.feedTitle')} help={t('calendar.feedHelp')}>
      <label>
        {t('calendar.feedAddress')}
        <span className="copy-field">
          <input readOnly value={url} onFocus={(e) => e.target.select()} />
          <button type="button" className="secondary" onClick={copy}>
            <Icon name={copied ? 'check' : 'copy'} small />
            {copied ? t('calendar.copied') : t('calendar.copy')}
          </button>
        </span>
      </label>
      <div className="settings-actions">
        <button type="button" className="link" onClick={replace}>
          {t('calendar.newAddress')}
        </button>
      </div>
    </SettingsRow>
  )
}
