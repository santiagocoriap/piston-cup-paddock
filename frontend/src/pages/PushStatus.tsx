import { useTranslation } from 'react-i18next'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
import { formatDateTime } from '../lib/format'

type Push = components['schemas']['PushOut']

// The reasons that the app knows. A collector older than 1.8.0 sends the Python error name.
const KNOWN = new Set([
  'server_running',
  'content_manager_open',
  'writing_disabled',
  'unknown_preset',
  'permission_denied',
  'file_missing',
  'bad_file',
  'bad_setup',
  'write_failed',
  'unexpected',
])
const OLD_NAMES: Record<string, string> = {
  PermissionError: 'permission_denied',
  FileNotFoundError: 'file_missing',
  KeyError: 'bad_setup',
  ValueError: 'bad_setup',
  OSError: 'write_failed',
}
// A push that waits longer than this, with a collector that did not call, is a problem.
const SILENT_MS = 90_000

/** The reason of a push, as "code:detail". */
export function pushReason(error: string): { code: string; detail: string } {
  const [raw, ...rest] = error.split(':')
  const code = OLD_NAMES[raw] ?? raw
  return { code: KNOWN.has(code) ? code : 'unexpected', detail: rest.join(':') || (KNOWN.has(code) ? '' : raw) }
}

/** The state of the last push: what happened, why, and what the admin can do now. */
export function PushStatus({ push, collectorSeenAt }: { push: Push; collectorSeenAt: string | null | undefined }) {
  const { t, i18n } = useTranslation()
  const date = formatDateTime(push.finished_at ?? push.requested_at, i18n.language)
  const now = Date.now()
  const silent =
    push.status === 'pending' &&
    now - new Date(push.requested_at).getTime() > SILENT_MS &&
    (!collectorSeenAt || now - new Date(collectorSeenAt).getTime() > SILENT_MS)

  if (push.status === 'done') {
    return (
      <p className="push-status ok" role="status">
        <Icon name="check" small />
        {t('serverPush.status.done', { date })}
      </p>
    )
  }
  if (push.status === 'cancelled') {
    return (
      <p className="muted" role="status">
        {t('serverPush.status.cancelled')}
      </p>
    )
  }
  if (push.status === 'pending' && !silent) {
    return (
      <p className="push-status" role="status">
        <span className="spinner" aria-hidden="true" />
        {t('serverPush.status.pending', { date })}
      </p>
    )
  }

  const { code, detail } = silent ? { code: 'collector_silent', detail: '' } : pushReason(push.error)
  const failed = push.status === 'failed'
  return (
    <div className={failed ? 'push-status-box failed' : 'push-status-box waiting'} role={failed ? 'alert' : 'status'}>
      <p className="push-status-title">
        <Icon name={failed ? 'alert' : 'clock'} small />
        <b>{failed ? t('serverPush.failedTitle', { date }) : t('serverPush.waitingTitle')}</b>
      </p>
      <p>{t(`serverPush.reasons.${code}.why`, { detail })}</p>
      <p className="push-status-fix">
        <b>{t('serverPush.whatToDo')}</b> {t(`serverPush.reasons.${code}.fix`, { detail })}
      </p>
      {collectorSeenAt && (
        <p className="muted">{t('serverPush.collectorSeen', { date: formatDateTime(collectorSeenAt, i18n.language) })}</p>
      )}
      {push.error && code === 'unexpected' && <code className="push-status-raw">{push.error}</code>}
    </div>
  )
}
