import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../../api/client'
import { Breadcrumbs } from '../../components/Breadcrumbs'
import { Icon, type IconName } from '../../components/Icon'
import { Loading } from '../../components/Layout'
import { auditSentence, formatAuditValue as formatValue, type AuditEntry } from '../../lib/audit'
import { currentTimeZone } from '../../lib/format'
import { dayKey, dayTitle as titleOfDay, nearDays } from '../../lib/days'
import { useLoad } from '../../lib/useLoad'

const TARGET_PATHS: Record<string, (id: number) => string> = {
  season: (id) => `/seasons/${id}`,
  round: (id) => `/rounds/${id}`,
  championship: (id) => `/championships/${id}`,
  driver: (id) => `/drivers/${id}`,
  track: () => '/admin/catalog',
  car: () => '/admin/catalog',
  league: () => '/admin/leagues',
}

// The API gives the last 200 changes when the page asks for no limit.
const API_LIMIT = 200

type Kind = 'results' | 'penalties' | 'season' | 'people' | 'catalog' | 'reports'

// The kind of a change comes from the first word of its action, for example "result" in "result.changed".
const KINDS: Record<string, Kind> = {
  result: 'results', import: 'results', penalty_logs: 'results', restart: 'results', lap: 'results', record: 'results',
  penalty: 'penalties', protest: 'penalties', incident: 'penalties',
  season: 'season', round: 'season', rules: 'season', handicap: 'season', entry: 'season', ballot: 'season',
  account: 'people', driver: 'people', member: 'people', role: 'people', career: 'people', collector: 'people',
  track: 'catalog', layout: 'catalog', car: 'catalog', class: 'catalog', catalog: 'catalog', league: 'catalog', championship: 'catalog',
  report: 'reports', backup: 'reports',
}
const ICONS: Record<Kind, IconName> = {
  results: 'flag', penalties: 'alert', season: 'layers', people: 'users', catalog: 'map', reports: 'info',
}
const KIND_ORDER: Kind[] = ['results', 'penalties', 'season', 'people', 'catalog', 'reports']

function kindOf(entry: AuditEntry): Kind | undefined {
  const prefix = entry.action.split('.')[0]
  return KINDS[prefix]
}

/** Changes in a row that say the same thing about the same target. The newest one leads. */
type Group = { lead: AuditEntry; more: AuditEntry[] }

function sameKind(a: AuditEntry, b: AuditEntry): boolean {
  const plain = (e: AuditEntry) => e.changes.length === 0 && !e.reason
  return (
    plain(a) && plain(b) && a.action === b.action && a.actor_name === b.actor_name &&
    a.target_type === b.target_type && a.target_id === b.target_id && a.championship_id === b.championship_id
  )
}

function groupByDay(entries: AuditEntry[]): { day: string; groups: Group[] }[] {
  const days: { day: string; groups: Group[] }[] = []
  for (const entry of entries) {
    const day = dayKey(entry.created_at)
    let current = days.at(-1)
    if (!current || current.day !== day) {
      current = { day, groups: [] }
      days.push(current)
    }
    const last = current.groups.at(-1)
    if (last && sameKind(last.lead, entry)) last.more.push(entry)
    else current.groups.push({ lead: entry, more: [] })
  }
  return days
}

export function AuditPage() {
  const { t, i18n } = useTranslation()
  const [championshipId, setChampionshipId] = useState('')
  const [kind, setKind] = useState<Kind | ''>('')
  const [query, setQuery] = useState('')
  // Today and yesterday, read once when the page opens.
  const [near] = useState(() => nearDays(Date.now()))
  const championships = useLoad(() => api.GET('/api/championships'), [])
  const audit = useLoad(
    () =>
      api.GET('/api/audit', {
        params: { query: championshipId ? { championship_id: Number(championshipId) } : {} },
      }),
    [championshipId],
  )

  const zone = currentTimeZone()
  const time = new Intl.DateTimeFormat(i18n.language, { timeStyle: 'short', timeZone: zone })
  const dayTitle = (day: string) =>
    titleOfDay(day, near, i18n.language, { today: t('audit.today'), yesterday: t('audit.yesterday') })


  const needle = query.trim().toLowerCase()
  const entries = (audit.data ?? []).filter((entry) => {
    if (kind && kindOf(entry) !== kind) return false
    if (!needle) return true
    return [auditSentence(t, entry), entry.actor_name, entry.reason, entry.championship_name ?? '']
      .some((text) => text.toLowerCase().includes(needle))
  })
  const days = groupByDay(entries)

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.audit') }]} />
      <header className="page-head">
        <div>
          <h1>{t('audit.title')}</h1>
          <p className="muted">{t('audit.help')}</p>
        </div>
      </header>

      <div className="forms record-filters" role="group" aria-label={t('audit.search')}>
        <label className="inline-filter">
          {t('audit.championship')}
          <select value={championshipId} onChange={(event) => setChampionshipId(event.target.value)}>
            <option value="">{t('audit.all')}</option>
            {championships.data
              ?.filter((c) => c.can_manage)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </label>
        <label className="inline-filter">
          {t('audit.search')}
          <span className="search-field">
            <Icon name="search" small />
            <input type="search" value={query} placeholder={t('audit.searchPlaceholder')} onChange={(e) => setQuery(e.target.value)} />
          </span>
        </label>
      </div>

      <div className="kind-chips" role="group" aria-label={t('audit.kindLabel')}>
        {(['', ...KIND_ORDER] as const).map((value) => (
          <button
            key={value || 'all'}
            type="button"
            className="kind-chip"
            aria-pressed={kind === value}
            onClick={() => setKind(value)}
          >
            {value && <Icon name={ICONS[value]} small />}
            {t(`audit.kinds.${value || 'all'}`)}
          </button>
        ))}
      </div>

      {!audit.data ? (
        <Loading failed={audit.failed} />
      ) : audit.data.length === 0 ? (
        <p className="muted">{t('audit.empty')}</p>
      ) : entries.length === 0 ? (
        <p className="muted">{t('audit.noMatch')}</p>
      ) : (
        <>
          <p className="muted audit-count">
            {t('audit.count', { count: entries.length })}
            {audit.data.length >= API_LIMIT && ` · ${t('audit.limitNote', { count: API_LIMIT })}`}
          </p>
          {days.map(({ day, groups }) => (
            <section key={day} className="audit-day" aria-label={dayTitle(day)}>
              <h2 className="audit-day-title">{dayTitle(day)}</h2>
              <ol className="audit-timeline">
                {groups.map(({ lead, more }) => (
                  <AuditItem key={lead.id} entry={lead} more={more} time={time} />
                ))}
              </ol>
            </section>
          ))}
        </>
      )}
    </section>
  )
}

function AuditItem({ entry, more, time }: { entry: AuditEntry; more: AuditEntry[]; time: Intl.DateTimeFormat }) {
  const { t } = useTranslation()
  const kind = kindOf(entry)
  const path = TARGET_PATHS[entry.target_type]?.(entry.target_id)
  const sentence = auditSentence(t, entry)
  return (
    <li className={`audit-item audit-${kind ?? 'other'}`}>
      <span className="audit-icon" aria-hidden="true">
        <Icon name={kind ? ICONS[kind] : 'history'} small />
      </span>
      <div className="audit-body">
        <div className="audit-head">
          <time dateTime={entry.created_at} className="muted">
            {time.format(new Date(entry.created_at))}
          </time>
          {entry.championship_name && <span className="badge chip">{entry.championship_name}</span>}
        </div>
        <p className="audit-sentence">{path ? <Link to={path}>{sentence}</Link> : sentence}</p>
        {entry.changes.length > 0 && (
          <ul className="audit-changes">
            {entry.changes.map((item, index) => (
              <li key={index}>
                <span className="audit-field">{t(`audit.fields.${item.field}`, { defaultValue: item.field })}</span>
                <span className="audit-old">{formatValue(t, item.old)}</span>
                <span className="audit-arrow" aria-hidden="true">
                  <Icon name="arrow" small />
                </span>
                <span className="audit-new">{formatValue(t, item.new)}</span>
              </li>
            ))}
          </ul>
        )}
        {entry.reason && (
          <blockquote className="audit-reason">
            <span className="audit-reason-label">{t('audit.reason')}</span>
            {entry.reason}
          </blockquote>
        )}
        {more.length > 0 && (
          <details className="audit-more">
            <summary>{t('audit.more', { count: more.length })}</summary>
            <ul>
              {more.map((other) => (
                <li key={other.id}>
                  <time dateTime={other.created_at} className="muted">
                    {time.format(new Date(other.created_at))}
                  </time>{' '}
                  {auditSentence(t, other)}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </li>
  )
}
