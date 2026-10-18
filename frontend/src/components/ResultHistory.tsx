import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { medal } from '../lib/medal'

/** One result of a driver in one round. */
export type Result = {
  round_id: number
  round_number: number
  track_name: string
  status: string
  position: number | null
  points: number
}

/** A medal class for the top 3, "out" (DNF, DNS, or DSQ), or "" for any other finish. */
function resultTone(result: Result): string {
  if (result.status !== 'finished') return 'out'
  return medal(result.position)
}

/** The results as chips: the round, the place, and the points. Gold, silver, and bronze for the
 * top 3, red for a DNF, a DNS, or a DSQ. */
export function ResultChips({ results }: { results: Result[] }) {
  const { t } = useTranslation()
  return (
    <ol className="result-chips">
      {results.map((result) => (
        <li key={result.round_id} className={`result-chip ${resultTone(result)}`.trim()}>
          <Link to={`/rounds/${result.round_id}`}>
            <span className="result-round">
              {t('round.title', { number: result.round_number })} · {result.track_name}
            </span>
            <span className="result-place num">
              {result.position ? `P${result.position}` : result.status.toUpperCase()}
              {result.status !== 'finished' && result.position ? ` ${result.status.toUpperCase()}` : ''}
            </span>
            <span className="result-points num">{t('dashboard.points', { count: result.points })}</span>
          </Link>
        </li>
      ))}
    </ol>
  )
}

/** The position in each round as a small line. P1 is at the top. */
export function Trend({ history, entries }: { history: Result[]; entries: number }) {
  const { t } = useTranslation()
  const placed = history.filter((r) => r.position !== null)
  if (placed.length < 2) return null
  const width = 400
  const height = 72
  const pad = 8
  const left = 34
  const worst = Math.max(2, entries, ...placed.map((r) => r.position ?? 1))
  const x = (index: number) => left + (index * (width - left - pad)) / (placed.length - 1)
  const y = (position: number) => pad + ((position - 1) * (height - 2 * pad)) / (worst - 1)
  const points = placed.map((r, index) => `${x(index)},${y(r.position ?? worst)}`).join(' ')
  const label = `${t('dashboard.trend')}: ${placed
    .map((r) => `${t('round.title', { number: r.round_number })} P${r.position}`)
    .join(', ')}`
  return (
    <svg className="trend" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <text className="trend-scale" x={0} y={y(1) + 4} aria-hidden="true">
        {t('dashboard.trendScale', { position: 1 })}
      </text>
      <text className="trend-scale" x={0} y={y(worst) + 4} aria-hidden="true">
        {t('dashboard.trendScale', { position: worst })}
      </text>
      <line className="trend-top" x1={left} x2={width - pad} y1={y(1)} y2={y(1)} />
      <polyline points={points} />
      {placed.map((r, index) => (
        <circle
          key={r.round_id}
          className={index === placed.length - 1 ? 'last' : undefined}
          cx={x(index)}
          cy={y(r.position ?? worst)}
          r={index === placed.length - 1 ? 4.5 : 3}
        >
          <title>{`${t('round.title', { number: r.round_number })} · P${r.position}`}</title>
        </circle>
      ))}
    </svg>
  )
}
