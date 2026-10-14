import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { AdminActions } from '../components/AdminActions'
import { Icon, type IconName } from '../components/Icon'
import { Loading } from '../components/Layout'
import { ResultChips, Trend } from '../components/ResultHistory'
import { ProfileStats } from './ProfileStats'
import { formatDateTime, formatLapTime } from '../lib/format'
import { medal } from '../lib/medal'
import { useLoad } from '../lib/useLoad'
import { useAdminView, useMe, useMode } from '../session'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { Avatar } from '../components/Avatar'

type Profile = components['schemas']['ProfileOut']
type Career = Profile['career']

const BADGE_ICONS: Record<string, IconName> = {
  win: 'trophy',
  podium: 'medal',
  pole: 'flag',
  fastest_lap: 'timer',
  starts: 'history',
  record: 'clock',
}

/** One driver: a hero card with the level, badges, recent results, the career by season,
 * safety, records, and restarts caused. An empty part is not shown. */
export function DriverProfilePage() {
  const { t } = useTranslation()
  const me = useMe()
  const { mode } = useMode()
  const driverId = Number(useParams().driverId)
  const load = useLoad(
    () => api.GET('/api/drivers/{driver_id}/profile', { params: { path: { driver_id: driverId } } }),
    [driverId],
  )
  const [override, setOverride] = useState<Profile | null>(null)
  const data = override ?? load.data
  const adminView = useAdminView(data?.can_adjust ?? false)
  // The admin list of drivers exists only for a league admin in the admin mode.
  const adminPages = me.is_admin && mode === 'admin'
  if (!data) return <Loading failed={load.failed} />
  const current = data.seasons[0]
  const newest = current ? [...current.history].reverse().slice(0, 5) : []

  return (
    <section className="profile-page">
      <Breadcrumbs
        items={[...(adminPages ? [{ label: t('nav.drivers'), to: '/admin/drivers' }] : []), { label: data.display_name }]}
      />

      <header className="profile-hero">
        <Avatar name={data.display_name} url={data.avatar_url} className="profile-avatar" />
        <div className="profile-who">
          <h1>{data.display_name}</h1>
          {current && (
            <p className="profile-entry">
              <span className="car-number">#{current.number}</span>
              {[current.car_name, current.team].filter(Boolean).join(' · ')}
            </p>
          )}
          {current && (
            <p className="muted">
              <Link to={`/seasons/${current.season_id}`}>
                {current.championship_name} · {current.season_name}
              </Link>
            </p>
          )}
        </div>
        <LevelRing career={data.career} />
        {adminView && (
          <div className="profile-admin">
            <AdminActions
              actions={[
                {
                  id: 'adjust',
                  label: t('profile.adjust'),
                  content: (close) => (
                    <AdjustForm
                      driverId={driverId}
                      career={data.career}
                      onSaved={(next) => {
                        setOverride(next)
                        close()
                      }}
                    />
                  ),
                },
              ]}
            />
          </div>
        )}
      </header>

      <ProfileStats stats={data.stats} />

      <section aria-labelledby="badges">
        <h2 id="badges">{t('profile.badges')}</h2>
        <ul className="badge-grid">
          {data.achievements.map((badge) => (
            <li key={badge.key} className={badge.achieved ? 'achieved' : 'locked'}>
              <span className="badge-icon" aria-hidden="true">
                <Icon name={BADGE_ICONS[badge.key] ?? 'trophy'} />
              </span>
              <span className="badge-text">
                <b>{t(`profile.badge.${badge.key}`)}</b>
                <span className="muted">
                  {badge.achieved
                    ? t('profile.badgeCount', { count: badge.count })
                    : t('profile.badgeGoal', { count: badge.count, goal: badge.goal })}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {current && current.history.length > 0 && (
        <section aria-labelledby="recent-results">
          <h2 id="recent-results">{t('profile.recent', { season: current.season_name })}</h2>
          <Trend history={current.history} entries={current.entries} />
          <ResultChips results={newest} />
        </section>
      )}

      <section aria-labelledby="career">
        <h2 id="career">{t('profile.seasons')}</h2>
        {data.seasons.length === 0 ? (
          <p className="muted">{t('profile.noSeasons')}</p>
        ) : (
          <ol className="career-timeline">
            {data.seasons.map((s) => (
              <li key={s.season_id} className={medal(s.rank) || undefined}>
                <span className="career-dot" aria-hidden="true">
                  {s.rank <= 3 ? <Icon name="medal" small /> : s.rank}
                </span>
                <div>
                  <Link to={`/seasons/${s.season_id}`}>
                    {s.championship_name} · {s.season_name}
                  </Link>
                  <p className="career-place">{t('profile.place', { rank: s.rank, entries: s.entries, points: s.points })}</p>
                  <p className="muted">
                    {[
                      t('profile.winsCount', { count: s.wins }),
                      t('profile.podiumsCount', { count: s.podiums }),
                      t('profile.startsCount', { count: s.starts }),
                      s.starts ? t('profile.perStartValue', { value: (s.points / s.starts).toFixed(1) }) : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {data.safety.length > 0 && (
        <section aria-labelledby="profile-safety">
          <h2 id="profile-safety">{t('profile.safety')}</h2>
          <ul className="safety-cards">
            {data.safety.map((s) => (
              <li key={s.championship_name} className="card">
                <p className="muted">{s.championship_name}</p>
                <p className="safety-big">
                  <b className={`safety-rating ${s.status}`}>{s.status === 'unknown' ? '—' : s.rating.toFixed(2)}</b>
                  <span className={`badge safety-${s.status}`}>{t(`safety.status.${s.status}`)}</span>
                </p>
                <p className="muted">{t('profile.safetyCounts', { laps: s.laps, points: s.points })}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.records.length > 0 && (
        <section aria-labelledby="profile-records">
          <h2 id="profile-records">{t('profile.records')}</h2>
          <ul className="list">
            {data.records.map((r) => (
              <li key={`${r.track}-${r.car}-${r.category}`}>
                <Link to={`/rounds/${r.round_id}`}>{r.track}</Link> · {r.car} · {t(`records.category.${r.category}`)} ·{' '}
                <strong>{formatLapTime(r.lap_time_ms)}</strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.restarts_caused.length > 0 && (
        <section aria-labelledby="profile-restarts">
          <h2 id="profile-restarts">{t('profile.restarts')}</h2>
          <ul className="list">
            {data.restarts_caused.map((r) => (
              <li key={`${r.round_id}-${r.attempt}`}>
                <Link to={`/rounds/${r.round_id}`}>{r.label}</Link> · {t('profile.attempt', { number: r.attempt })} ·{' '}
                {t(`restarts.reasons.${r.reason}`)}
                {r.shared && <span className="badge">{t('restarts.sharedBadge')}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  )
}

/** The level in a ring. The ring fills with the points toward the next level. */
function LevelRing({ career }: { career: Career }) {
  const { t } = useTranslation()
  const start = (career.level - 1) * 100
  const share = Math.min(1, Math.max(0, (career.points - start) / (career.next_level_points - start || 100)))
  const radius = 40
  const length = 2 * Math.PI * radius
  return (
    <div className="level-ring">
      <svg viewBox="0 0 100 100" role="img" aria-label={t('profile.levelLabel', { level: career.level, points: career.points, next: career.next_level_points })}>
        <circle className="level-track" cx="50" cy="50" r={radius} />
        <circle
          className="level-fill"
          cx="50"
          cy="50"
          r={radius}
          strokeDasharray={length}
          strokeDashoffset={length * (1 - share)}
        />
        <text x="50" y="47" textAnchor="middle" className="level-number" aria-hidden="true">
          {career.level}
        </text>
        <text x="50" y="64" textAnchor="middle" className="level-word" aria-hidden="true">
          {t('profile.levelWord')}
        </text>
      </svg>
      <p>
        <b>{t('profile.pointsOf', { points: career.points, next: career.next_level_points })}</b>
        <span className="muted">{t('profile.officialOnly')}</span>
        {career.points !== career.raw_points && (
          <span className="muted">{t('profile.raw', { points: career.raw_points })}</span>
        )}
      </p>
    </div>
  )
}

function AdjustForm({
  driverId,
  career,
  onSaved,
}: {
  driverId: number
  career: Career
  onSaved: (next: Profile) => void
}) {
  const { t, i18n } = useTranslation()
  return (
    <>
      <ActionForm
        title={t('profile.adjust')}
        submitLabel={t('common.save')}
        onSubmit={async (form) => {
          const kind = form.get('kind') as 'adjust' | 'reset'
          const { data: next, error } = await api.POST('/api/drivers/{driver_id}/career', {
            params: { path: { driver_id: driverId } },
            body: { kind, points: Number(form.get('points') || 0), reason: String(form.get('reason')) },
          })
          if (next) onSaved(next)
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
    </>
  )
}
