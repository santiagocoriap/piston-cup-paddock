import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

const GHOST_ROWS = [72, 58, 64, 50, 68, 54]

type Props = { icon: IconName; title: string; text: string; children?: ReactNode }

/** An empty list. Faded sample rows move behind the text to show what will be here. */
export function EmptyState({ icon, title, text, children }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state-rows" aria-hidden="true">
        {[0, 1].map((copy) => (
          <div key={copy} className="empty-state-track">
            {GHOST_ROWS.map((width, i) => (
              <div key={i} className="empty-state-row">
                <span className="ghost-dot" />
                <span className="ghost-bar" style={{ width: `${width}%` }} />
                <span className="ghost-time" />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="empty-state-body">
        <span className="empty-state-icon">
          <Icon name={icon} />
        </span>
        <p className="empty-state-title">{title}</p>
        <p className="muted">{text}</p>
        {children}
      </div>
    </div>
  )
}
