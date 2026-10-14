import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, type IconName } from './Icon'
import { Logo } from './Logo'

// A made-up circuit for the picture. The line draws itself, and a dot drives the lap.
const TRACK =
  'M70 230 C60 150 110 70 200 70 C270 70 280 125 330 120 C380 115 380 215 315 232 C255 248 245 195 180 205 C130 213 135 255 100 255 C82 255 72 246 70 230 Z'

const FEATURES: { icon: IconName; key: string }[] = [
  { icon: 'flag', key: 'results' },
  { icon: 'shield', key: 'penalties' },
  { icon: 'check', key: 'votes' },
]

/** The page around the sign-in and invitation forms: the brand side and the form side.
 * On a phone, the brand side is a short band on top. */
export function AuthShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="auth">
      <aside className="auth-aside" aria-label={t('app.name')}>
        <div className="auth-brand">
          <Logo size={44} />
        </div>
        <svg className="auth-track" viewBox="0 0 440 320" aria-hidden="true">
          <path className="auth-track-base" d={TRACK} />
          <path className="auth-track-line" d={TRACK} pathLength={1} />
          <circle className="auth-car" r="7">
            <animateMotion dur="9s" repeatCount="indefinite" path={TRACK} />
          </circle>
        </svg>
        <div className="auth-copy">
          <h2>{t('auth.tagline')}</h2>
          <ul>
            {FEATURES.map((feature) => (
              <li key={feature.key}>
                <span className="auth-feature-icon">
                  <Icon name={feature.icon} small />
                </span>
                {t(`auth.features.${feature.key}`)}
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <main className="auth-main">
        <div className="auth-panel">{children}</div>
      </main>
    </div>
  )
}
