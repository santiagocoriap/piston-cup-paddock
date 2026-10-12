import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../../api/client'
import { Loading } from '../../components/Layout'
import { auditSentence, formatAuditValue as formatValue } from '../../lib/audit'
import { formatDateTime } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

const TARGET_PATHS: Record<string, (id: number) => string> = {
  season: (id) => `/seasons/${id}`,
  round: (id) => `/rounds/${id}`,
  championship: (id) => `/championships/${id}`,
  driver: () => '/admin/drivers',
  track: () => '/admin/catalog',
  car: () => '/admin/catalog',
  league: () => '/admin/leagues',
}

export function AuditPage() {
  const { t, i18n } = useTranslation()
  const [championshipId, setChampionshipId] = useState('')
  const championships = useLoad(() => api.GET('/api/championships'), [])
  const audit = useLoad(
    () =>
      api.GET('/api/audit', {
        params: { query: championshipId ? { championship_id: Number(championshipId) } : {} },
      }),
    [championshipId],
  )

  return (
    <section>
      <h1>{t('audit.title')}</h1>
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

      {!audit.data ? (
        <Loading failed={audit.failed} />
      ) : audit.data.length === 0 ? (
        <p>{t('audit.empty')}</p>
      ) : (
        <ol className="audit">
          {audit.data.map((entry) => {
            const path = TARGET_PATHS[entry.target_type]?.(entry.target_id)
            const sentence = auditSentence(t, entry)
            return (
              <li key={entry.id}>
                <div className="audit-head">
                  <time dateTime={entry.created_at} className="muted">
                    {formatDateTime(entry.created_at, i18n.language)}
                  </time>
                  {entry.championship_name && <span className="badge">{entry.championship_name}</span>}
                </div>
                <p>{path ? <Link to={path}>{sentence}</Link> : sentence}</p>
                {entry.changes.length > 0 && (
                  <ul className="changes">
                    {entry.changes.map((item, index) => (
                      <li key={index}>
                        <strong>{t(`audit.fields.${item.field}`, { defaultValue: item.field })}</strong>:{' '}
                        <span className="muted">{formatValue(t, item.old)}</span> →{' '}
                        {formatValue(t, item.new)}
                      </li>
                    ))}
                  </ul>
                )}
                {entry.reason && (
                  <p className="reason">
                    {t('audit.reason')}: {entry.reason}
                  </p>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
