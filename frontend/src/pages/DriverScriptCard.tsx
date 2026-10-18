import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Setup = components['schemas']['ScriptSetupOut']

/** The Paddock script for the drivers: the text that the admin pastes in the CSP options of
 * the server. With it, AC sends the laps of each driver with no program to install. */
export function DriverScriptCard({ championshipId }: { championshipId: number }) {
  const { t, i18n } = useTranslation()
  const path = { championship_id: championshipId }
  const load = useLoad(() => api.GET('/api/championships/{championship_id}/script', { params: { path } }), [championshipId])
  const [override, setOverride] = useState<Setup | null>(null)
  const [copied, setCopied] = useState(false)
  const data = override ?? load.data
  if (!data) return null

  async function copy() {
    await navigator.clipboard?.writeText(data!.csp_section)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  async function replace() {
    if (!window.confirm(t('driverScript.confirmNew'))) return
    const { data: next } = await api.POST('/api/championships/{championship_id}/script/code', { params: { path } })
    if (next) setOverride(next)
  }

  return (
    <div className="card" role="region" aria-label={t('driverScript.title')}>
      <h3>{t('driverScript.title')}</h3>
      <p className="muted">{t('driverScript.help')}</p>
      <ol className="driver-script-steps">
        <li>{t('driverScript.step1')}</li>
        <li>{t('driverScript.step2')}</li>
        <li>{t('driverScript.step3')}</li>
      </ol>
      <pre className="mono csp-section" aria-label={t('driverScript.section')}>
        {data.csp_section}
      </pre>
      <div className="driver-script-actions">
        <button type="button" className="secondary" onClick={copy}>
          <Icon name={copied ? 'check' : 'copy'} small />
          {copied ? t('calendar.copied') : t('driverScript.copy')}
        </button>
        <button type="button" className="link" onClick={replace}>
          {t('driverScript.newCode')}
        </button>
      </div>
      <p className="muted">{t('driverScript.codeDate', { date: formatDateTime(data.created_at, i18n.language) })}</p>
    </div>
  )
}
