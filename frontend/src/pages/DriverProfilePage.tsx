import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { Loading } from '../components/Layout'
import { formatDateTime, formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useAdminView } from '../session'

type Profile = components['schemas']['ProfileOut']

/** One driver: career level, seasons, safety, records, and restarts caused. */
export function DriverProfilePage() {
  const { t, i18n } = useTranslation()
  const driverId = Number(useParams().driverId)
  const load = useLoad(
    () => api.GET('/api/drivers/{driver_id}/profile', { params: { path: { driver_id: driverId } } }),
    [driverId],
  )
  const [override, setOverride] = useState<Profile | null>(null)
  const data = override ?? load.data
  const adminView = useAdminView(data?.can_adjust ?? false)
  if (!data) return <Loading failed={load.failed} />
  const career = data.career
  const progress = Math.round(((career.points % 100) / 100) * 100)

  return (
    <section>
      <h1>{data.display_name}</h1>
      <div className="stats">
        <div>
          <span className="stat-label">{t('profile.level')}</span>
          <span className="stat-value">{career.level}</span>
        </div>
        <div>
          <span className="stat-label">{t('profile.careerPoints')}</span>
          <span className="stat-value">{career.points}</span>
        </div>
      </div>
      <p className="muted">
        {t('profile.nextLevel', { points: career.next_level_points, progress })}
        {career.points !== career.raw_points && ` · ${t('profile.raw', { points: career.raw_points })}`}
      </p>

      <h2>{t('profile.seasons')}</h2>
      {data.seasons.length === 0 ? (
        <p className="muted">{t('profile.noSeasons')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('profile.season')}</th>
                <th scope="col">{t('standings.rank')}</th>
                <th scope="col">{t('standings.points')}</th>
                <th scope="col">{t('standings.wins')}</th>
                <th scope="col">{t('profile.podiums')}</th>
                <th scope="col">{t('profile.starts')}</th>
                <th scope="col">{t('profile.perStart')}</th>
              </tr>
            </thead>
            <tbody>
              {data.seasons.map((s) => (
                <tr key={s.season_id}>
                  <td>
                    <Link to={`/seasons/${s.season_id}`}>
                      {s.championship_name} · {s.season_name}
                    </Link>
                  </td>
                  <td>
                    {s.rank} / {s.entries}
                  </td>
                  <td>{s.points}</td>
                  <td>{s.wins}</td>
                  <td>{s.podiums}</td>
                  <td>{s.starts}</td>
                  <td>{s.starts ? (s.points / s.starts).toFixed(1) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>{t('profile.safety')}</h2>
      <ul className="list">
        {data.safety.map((s) => (
          <li key={s.championship_name}>
            {s.championship_name}: {s.status === 'unknown' ? '—' : s.rating.toFixed(2)}{' '}
            <span className="badge">{t(`safety.status.${s.status}`)}</span> ·{' '}
            {t('profile.safetyCounts', { laps: s.laps, points: s.points })}
          </li>
        ))}
      </ul>

      <h2>{t('profile.records')}</h2>
      {data.records.length === 0 ? (
        <p className="muted">{t('profile.noRecords')}</p>
      ) : (
        <ul className="list">
          {data.records.map((r) => (
            <li key={`${r.track}-${r.car}-${r.category}`}>
              <Link to={`/rounds/${r.round_id}`}>{r.track}</Link> · {r.car} · {t(`records.category.${r.category}`)} ·{' '}
              <strong>{formatLapTime(r.lap_time_ms)}</strong>
            </li>
          ))}
        </ul>
      )}

      <h2>{t('profile.restarts')}</h2>
      {data.restarts_caused.length === 0 ? (
        <p className="muted">{t('profile.noRestarts')}</p>
      ) : (
        <ul className="list">
          {data.restarts_caused.map((r) => (
            <li key={`${r.round_id}-${r.attempt}`}>
              <Link to={`/rounds/${r.round_id}`}>{r.label}</Link> · {t('profile.attempt', { number: r.attempt })} ·{' '}
              {t(`restarts.reasons.${r.reason}`)}
              {r.shared && <span className="badge">{t('restarts.sharedBadge')}</span>}
            </li>
          ))}
        </ul>
      )}

      {adminView && (
        <div className="forms">
          <ActionForm
            title={t('profile.adjust')}
            submitLabel={t('common.save')}
            onSubmit={async (form) => {
              const kind = form.get('kind') as 'adjust' | 'reset'
              const { data: next, error } = await api.POST('/api/drivers/{driver_id}/career', {
                params: { path: { driver_id: driverId } },
                body: { kind, points: Number(form.get('points') || 0), reason: String(form.get('reason')) },
              })
              if (next) setOverride(next)
              return error
            }}
          >
            <label>
              {t('profile.adjustKind')}
              <select name="kind" defaultValue="adjust">
                <option value="adjust">{t('profile.kinds.adjust')}</option>
                <option value="reset">{t('profile.kinds.reset')}</option>
              </select>
            </label>
            <label>
              {t('profile.adjustPoints')}
              <input name="points" type="number" min={-10000} max={10000} defaultValue={0} />
            </label>
            <label>
              {t('profile.reason')}
              <input name="reason" required maxLength={500} />
            </label>
          </ActionForm>
          {career.adjustments.length > 0 && (
            <div className="card">
              <h3>{t('profile.adjustments')}</h3>
              <ul className="list">
                {career.adjustments.map((a, index) => (
                  <li key={index}>
                    {formatDateTime(a.created_at, i18n.language)} · {t(`profile.kinds.${a.kind}`)}
                    {a.kind === 'adjust' && ` ${a.points > 0 ? '+' : ''}${a.points}`} · {a.reason}
                    {a.created_by && ` · ${a.created_by}`}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
