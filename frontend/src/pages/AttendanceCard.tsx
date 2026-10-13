import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'

type Attendance = components['schemas']['AttendanceOut']
type Answer = 'yes' | 'maybe' | 'no'

/** Who comes to the round. A driver of the season answers until the round starts. */
export function AttendanceCard({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const load = useLoad(
    () => api.GET('/api/rounds/{round_id}/attendance', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const [override, setOverride] = useState<Attendance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const data = override ?? load.data
  if (!data) return null

  async function answer(value: Answer) {
    setError(null)
    const { data: next, error } = await api.PUT('/api/rounds/{round_id}/attendance', {
      params: { path: { round_id: roundId } },
      body: { answer: value },
    })
    if (next) setOverride(next)
    else setError(errorMessage(t, error))
  }

  return (
    <div className="card" role="region" aria-label={t('attendance.title')}>
      <h3>{t('attendance.title')}</h3>
      <p>{t('attendance.counts', { yes: data.yes, maybe: data.maybe, no: data.no })}</p>
      {data.can_answer && (
        <div className="tabs" role="group" aria-label={t('attendance.question')}>
          {(['yes', 'maybe', 'no'] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={data.mine === value}
              className={data.mine === value ? 'active' : undefined}
              onClick={() => answer(value)}
            >
              {t(`attendance.answers.${value}`)}
            </button>
          ))}
        </div>
      )}
      <details>
        <summary>{t('attendance.list')}</summary>
        <ul>
          {data.rows.map((row) => (
            <li key={row.entry_id}>
              {row.driver_name}: {row.answer ? t(`attendance.answers.${row.answer}`) : t('attendance.noAnswer')}
            </li>
          ))}
        </ul>
      </details>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}
