import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Health = components['schemas']['HealthOut']

/** Collector status, missing data of recent rounds, and failed tasks, in one card. */
export function HealthSection({ championshipId }: { championshipId: number }) {
  const { t, i18n } = useTranslation()
  const load = useLoad(
    () => api.GET('/api/championships/{championship_id}/health', { params: { path: { championship_id: championshipId } } }),
    [championshipId],
  )
  const [override, setOverride] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const data = override ?? load.data
  if (!data) return null

  async function retry(kind: string, id: number) {
    setError(null)
    const { data: next, error } =
      kind === 'report'
        ? await api.POST('/api/reports/{report_id}/retry', { params: { path: { report_id: id } } })
        : await api.POST('/api/championships/{championship_id}/jobs/{job_id}/retry', {
            params: { path: { championship_id: championshipId, job_id: id } },
          })
    if (next) setOverride(next)
    else setError(errorMessage(t, error))
  }

  const date = (value: string | null | undefined) => formatDateTime(value, i18n.language)

  return (
    <div className="card" role="region" aria-label={t('health.title')}>
      <h3>{t('health.title')}</h3>

      <h4>{t('health.collectors')}</h4>
      {data.collectors.length === 0 ? (
        <p className="muted">{t('health.noCollectors')}</p>
      ) : (
        <ul className="list">
          {data.collectors.map((collector) => (
            <li key={collector.id}>
              <strong>{collector.name}</strong>{' '}
              <span className={`badge health-${collector.status}`}>{t(`health.status.${collector.status}`)}</span> ·{' '}
              {t('health.lastSeen', { date: date(collector.last_seen_at) })} ·{' '}
              {t('health.lastFile', { date: date(collector.last_file_at) })} ·{' '}
              {t('health.lastEvent', { date: date(collector.last_event_at) })}
            </li>
          ))}
        </ul>
      )}
      {data.unmatched_files > 0 && <p className="warning">{t('health.unmatched', { count: data.unmatched_files })}</p>}

      <h4>{t('health.rounds')}</h4>
      {data.rounds.length === 0 && <p className="muted">{t('health.noRounds')}</p>}
      <ul className="list">
        {data.rounds.map((round) => (
          <li key={round.id}>
            <Link to={`/rounds/${round.id}`}>
              {round.season_name} R{round.number} · {round.track_name}
            </Link>{' '}
            {round.problems.length === 0 ? (
              <span className="success">✓ {t('health.complete')}</span>
            ) : (
              <ul>
                {round.problems.map((problem) => (
                  <li key={problem} className="warning">
                    {t(`health.problems.${problem}`, round.counts)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>

      <h4>{t('health.failed')}</h4>
      {data.failed.length === 0 ? (
        <p className="muted">{t('health.noFailed')}</p>
      ) : (
        <ul className="list">
          {data.failed.map((task) => (
            <li key={`${task.kind}-${task.id}`}>
              {t(`health.kind.${task.kind}`)} · {task.label} · {task.error} · {date(task.at)}{' '}
              <button type="button" className="link-button" onClick={() => retry(task.kind, task.id)}>
                {t('health.retry')}
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
    </div>
  )
}
