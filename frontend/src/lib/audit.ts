import type { TFunction } from 'i18next'
import type { components } from '../api/schema'

export type AuditEntry = components['schemas']['AuditEntryOut']
type Value = AuditEntry['changes'][number]['old']

/** Turn an audit entry into a sentence in the user's language. */
export function auditSentence(t: TFunction, entry: AuditEntry): string {
  const params = { actor: entry.actor_name, action: entry.action, ...entry.params }
  const key = `audit.actions.${entry.action}`
  return t(key, { ...params, defaultValue: t('audit.actions.unknown', params) })
}

export function formatAuditValue(t: TFunction, value: Value): string {
  if (value === null || value === undefined || value === '') return t('audit.none')
  if (typeof value === 'object') {
    // A result line: status, position, and points.
    const line = value as { status?: string; position?: number | null; points?: number }
    const place = line.position ? `P${line.position}` : ''
    const status = line.status && line.status !== 'finished' ? line.status.toUpperCase() : ''
    return [status, place, t('audit.pts', { count: line.points ?? 0 })].filter(Boolean).join(' · ')
  }
  return String(value)
}

