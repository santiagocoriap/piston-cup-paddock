import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Status = components['schemas']['BackupStatusOut']

const size = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`

const BADGE: Record<string, string> = { ok: 'health-running', failed: 'health-stopped' }

/** The last backup and a button to start one. For league admins only. */
export function BackupStatus() {
  const { t, i18n } = useTranslation()
  const load = useLoad(() => api.GET('/api/backups/status'), [])
  const [override, setOverride] = useState<Status | null>(null)
  const [error, setError] = useState<string | null>(null)
  const data = override ?? load.data
  if (!data) return null
  const last = data.last
  const running = last?.status === 'running'

  async function start() {
    setError(null)
    const { data: next, error } = await api.POST('/api/backups')
    if (next) setOverride(next)
    else setError(errorMessage(t, error))
  }

  async function refresh() {
    setOverride(null)
    load.reload()
  }

  return (
    <>
      <h4>{t('backup.title')}</h4>
      {!last ? (
        <p className="warning">{t('backup.never')}</p>
      ) : (
        <p>
          <span className={`badge ${BADGE[last.status] ?? ''}`}>
            {t(`backup.status.${last.status}`)}
          </span>{' '}
          {formatDateTime(last.finished_at ?? last.started_at, i18n.language)}
          {last.status === 'ok' && last.size_bytes !== null && (
            <> · {size(last.size_bytes)} · {t('backup.contents', { rows: last.rows, files: last.files })}</>
          )}
          {last.status === 'failed' && <> · {last.error}</>}
          {last.started_by && <> · {t('backup.by', { name: last.started_by })}</>}
        </p>
      )}
      {last?.status === 'failed' && data.last_ok_at && (
        <p className="muted">{t('backup.lastOk', { date: formatDateTime(data.last_ok_at, i18n.language) })}</p>
      )}
      <button type="button" className="secondary small" onClick={start} disabled={running}>
        {t('backup.start')}
      </button>{' '}
      {running && (
        <button type="button" className="link-button" onClick={refresh}>
          {t('backup.refresh')}
        </button>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </>
  )
}
