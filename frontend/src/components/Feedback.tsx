import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, type IconName } from './Icon'

type Status =
  | 'provisional'
  | 'official'
  | 'canceled'
  | 'pending'
  | 'confirmed'
  | 'accepted'
  | 'abandoned'
  | 'technical'
  | 'unknown'
  | 'failed'
  | 'new'

const STATUS_ICON: Partial<Record<Status, IconName>> = {
  provisional: 'clock',
  pending: 'clock',
  official: 'check',
  confirmed: 'check',
  accepted: 'flag',
  canceled: 'ban',
  failed: 'alert',
  abandoned: 'rotate',
  technical: 'alert',
  unknown: 'help',
}

/** A state shown with an icon, a word and a colour. Colour is never the only signal. */
export function StatusBadge({ status, children }: { status: Status; children: ReactNode }) {
  const icon = STATUS_ICON[status]
  return (
    <span className={`badge status-badge ${status}`}>
      {icon && <Icon name={icon} small />}
      {children}
    </span>
  )
}

/** The "What does it mean?" control: a button that opens an inline note. It never depends on hover. */
export function Explainer({ title, children, label }: { title: string; children: ReactNode; label?: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <span className="explainer">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <Icon name="help" small />
        {label ?? t('explain.what')}
      </button>
      <span className="explainer-panel" id={id} role="note" hidden={!open}>
        <strong>{title}:</strong> {children}
      </span>
    </span>
  )
}

const STATE_ICON: Record<string, IconName> = {
  loading: 'loader',
  empty: 'info',
  error: 'alert',
  restricted: 'lock',
  neutral: 'info',
}

/** Tells the person what is missing, why, and what to do. */
export function DataState({
  kind = 'neutral',
  title,
  children,
}: {
  kind?: 'loading' | 'empty' | 'error' | 'restricted' | 'neutral'
  title: string
  children?: ReactNode
}) {
  return (
    <div className={`data-state ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <span className="ds-icon">
        <Icon name={STATE_ICON[kind]} />
      </span>
      <div>
        <p className="ds-title">{title}</p>
        {children && <p className="ds-body">{children}</p>}
      </div>
    </div>
  )
}
