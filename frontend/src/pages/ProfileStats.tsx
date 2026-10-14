import { useTranslation } from 'react-i18next'
import type { components } from '../api/schema'

type Stats = components['schemas']['StatsOut']

/** The numbers of a career in 3 groups: results, totals, and mistakes. An empty value is a dash. */
export function ProfileStats({ stats }: { stats: Stats }) {
  const { t, i18n } = useTranslation()
  const number = (value: number | null, digits = 0) =>
    value === null ? '—' : new Intl.NumberFormat(i18n.language, { maximumFractionDigits: digits }).format(value)
  const groups: { title: string; tone?: string; items: [string, string][] }[] = [
    {
      title: t('stats.results'),
      items: [
        [t('stats.starts'), number(stats.starts)],
        [t('stats.wins'), number(stats.wins)],
        [t('stats.podiums'), number(stats.podiums)],
        [t('stats.top5'), number(stats.top5)],
        [t('stats.poles'), number(stats.poles)],
        [t('stats.fastestLaps'), number(stats.fastest_laps)],
        [t('stats.bestFinish'), stats.best_finish === null ? '—' : `P${stats.best_finish}`],
        [t('stats.averageFinish'), stats.average_finish === null ? '—' : `P${number(stats.average_finish, 1)}`],
      ],
    },
    {
      title: t('stats.totals'),
      items: [
        [t('stats.points'), number(stats.points)],
        [t('stats.laps'), number(stats.laps)],
        [t('stats.records'), number(stats.records)],
        [t('stats.winRate'), stats.win_rate === null ? '—' : `${number(stats.win_rate)} %`],
      ],
    },
    {
      title: t('stats.mistakes'),
      tone: 'warn',
      items: [
        [t('stats.dnfs'), number(stats.dnfs)],
        [t('stats.dsqs'), number(stats.dsqs)],
        [t('stats.penalties'), number(stats.penalties)],
        [t('stats.incidentPoints'), number(stats.incident_points)],
        [t('stats.restartsCaused'), number(stats.restarts_caused)],
      ],
    },
  ]
  return (
    <section aria-labelledby="profile-stats">
      <h2 id="profile-stats">{t('stats.title')}</h2>
      <div className="stat-groups">
        {groups.map((group) => (
          <div key={group.title} className={group.tone === 'warn' ? 'stat-group warn' : 'stat-group'}>
            <h3>{group.title}</h3>
            <dl className="stat-tiles">
              {group.items.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd className={group.tone === 'warn' && value !== '0' && value !== '—' ? 'bad' : undefined}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
      <p className="muted stat-note">{t('stats.note')}</p>
    </section>
  )
}
