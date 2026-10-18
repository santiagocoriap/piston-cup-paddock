import type { ReactNode } from 'react'

export type Message = { kind: 'error' | 'saved'; text: string } | null

/** One part of the settings: a title and a help text on the left, the controls on the right. */
export function SettingsRow({ id, title, help, children }: { id: string; title: string; help?: ReactNode; children: ReactNode }) {
  return (
    <section className="settings-row" aria-labelledby={id}>
      <div className="settings-intro">
        <h2 id={id}>{title}</h2>
        {help && <p className="muted">{help}</p>}
      </div>
      <div className="card settings-card">{children}</div>
    </section>
  )
}

/** A saved message or an error under a form. */
export function Feedback({ message }: { message: Message }) {
  if (!message) return null
  return (
    <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
      {message.text}
    </p>
  )
}
