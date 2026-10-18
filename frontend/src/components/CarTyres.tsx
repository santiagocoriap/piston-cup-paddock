import { useTranslation } from 'react-i18next'
import type { components } from '../api/schema'

type Car = components['schemas']['CarOut']
type Tyre = Car['tyres'][number]
type Side = Tyre['front']
type Wear = NonNullable<Side['wear']>

const mm = (metres?: number | null) => (metres ? Math.round(metres * 1000) : '–')
const size = (side: Side) => `${mm(side.width)}/R${mm(side.radius)}`
const units = (value: number) => Math.round(value * 10) / 10

/** How long a compound lasts, as one number to compare compounds: the wear where the grip falls
 * under 90 percent, or the whole curve when it never does. The unit is the game's own. */
function life(wear: Wear | null | undefined): number | null {
  return wear ? (wear.x_90 ?? wear.end_x) : null
}

/** The grip curve of a compound: wear on the horizontal axis, grip (0 to 100 percent of the
 * best point) on the vertical one. */
function WearChart({ wear }: { wear: Wear }) {
  const last = wear.curve[wear.curve.length - 1]?.[0] || 1
  const first = wear.curve[0]?.[0] ?? 0
  const span = last - first || 1
  const points = wear.curve
    .map(([x, grip]) => `${(((x - first) / span) * 100).toFixed(1)},${(40 - grip * 36).toFixed(1)}`)
    .join(' ')
  return (
    <svg className="wear-chart" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" x2="100" y1={40 - 0.9 * 36} y2={40 - 0.9 * 36} className="wear-guide" />
      <polyline points={points} fill="none" />
    </svg>
  )
}

function WearBlock({ tyre, longest }: { tyre: Tyre; longest: number }) {
  const { t } = useTranslation()
  const front = tyre.front.wear
  const rear = tyre.rear.wear
  // One curve when both axles use the same file, else one for each axle.
  const same = tyre.front.wear_curve === tyre.rear.wear_curve
  const curves = [
    { label: same ? '' : t('carDetail.front'), wear: front },
    ...(same ? [] : [{ label: t('carDetail.rear'), wear: rear }]),
  ].filter((item): item is { label: string; wear: Wear } => !!item.wear)
  if (curves.length === 0) return <p className="muted">{t('tyres.noWear')}</p>
  const shortest = Math.min(...curves.map((item) => life(item.wear)!))
  return (
    <div className="tyre-wear">
      <div className="wear-bar" title={t('tyres.relative')}>
        <span style={{ width: `${Math.max(4, Math.round((shortest / longest) * 100))}%` }} />
      </div>
      {curves.map(({ label, wear }) => (
        <div key={label} className="wear-curve">
          <WearChart wear={wear} />
          <p className="muted">
            {label && <b>{label}: </b>}
            {wear.x_95 == null
              ? t('tyres.holds95', { end: units(wear.end_x), grip: Math.round(wear.end_grip * 100) })
              : t('tyres.drops', {
                  x95: units(wear.x_95),
                  x90: wear.x_90 == null ? '–' : units(wear.x_90),
                  x80: wear.x_80 == null ? '–' : units(wear.x_80),
                })}
          </p>
        </div>
      ))}
    </div>
  )
}

/** The tyre compounds of a car: size, ideal pressure, and how the grip falls with wear. The bar
 * compares the compounds of the car with the one that lasts longest. */
export function CarTyres({ tyres }: { tyres: Tyre[] }) {
  const { t } = useTranslation()
  const longest = Math.max(1e-9, ...tyres.map((tyre) => Math.max(life(tyre.front.wear) ?? 0, life(tyre.rear.wear) ?? 0)))
  return (
    <ul className="tyre-list">
      {tyres.map((tyre) => (
        <li key={tyre.index}>
          <div className="tyre-head">
            <b>{tyre.name || `#${tyre.index}`}</b>
            {tyre.short_name && <span className="badge chip">{tyre.short_name}</span>}
          </div>
          <dl className="tyre-facts">
            <div>
              <dt>{t('carDetail.front')}</dt>
              <dd>{size(tyre.front)}</dd>
            </div>
            <div>
              <dt>{t('carDetail.rear')}</dt>
              <dd>{size(tyre.rear)}</dd>
            </div>
            <div>
              <dt>{t('carDetail.pressure')}</dt>
              <dd>{tyre.front.pressure_ideal ?? '–'} psi</dd>
            </div>
          </dl>
          <WearBlock tyre={tyre} longest={longest} />
        </li>
      ))}
    </ul>
  )
}
