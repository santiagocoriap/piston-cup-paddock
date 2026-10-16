import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { readCookie } from '../api/client'
import { errorMessage } from '../lib/errors'
import { Dialog } from './Dialog'
import { Icon } from './Icon'

export type DeleteKind =
  | 'league'
  | 'championship'
  | 'season'
  | 'round'
  | 'entry'
  | 'ballot'
  | 'driver'
  | 'user'
  | 'track'
  | 'layout'
  | 'car'
  | 'car_class'

// A container goes with everything inside it: the admin types its name to confirm.
const TYPE_NAME: DeleteKind[] = ['league', 'championship', 'season']

export type DeleteTarget = { kind: DeleteKind; id: number; name: string }

/** The confirmation of a delete. It says what goes with the thing, and the red button deletes
 * it. A track, car, or driver that races use stays: the window then says where it is in use. */
export function ConfirmDelete({
  target,
  onClose,
  onDeleted,
}: {
  target: DeleteTarget | null
  onClose: () => void
  onDeleted: () => void
}) {
  const { t } = useTranslation()
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uses, setUses] = useState<string[]>([])
  const mustType = target ? TYPE_NAME.includes(target.kind) : false
  const ready = !mustType || typed.trim() === target?.name.trim()

  function close() {
    setTyped('')
    setError(null)
    setUses([])
    onClose()
  }

  async function remove() {
    if (!target) return
    setBusy(true)
    setError(null)
    setUses([])
    try {
      // The typed client has no DELETE body here: a plain fetch, as for the file uploads.
      const response = await fetch(`/api/objects/${target.kind}/${target.id}`, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
      })
      const body = await response.json().catch(() => null)
      if (response.ok) {
        close()
        onDeleted()
        return
      }
      if (response.status === 409 && body?.uses) {
        setError(t(`deletion.errors.${body.detail}`))
        setUses(body.uses as string[])
      } else setError(errorMessage(t, body))
    } finally {
      setBusy(false)
    }
  }

  const use = (text: string) => {
    const [what, ...rest] = text.split(':')
    return t(`deletion.uses.${what}`, { value: rest.join(':') })
  }

  return (
    <Dialog open={target !== null} title={t('deletion.title', { name: target?.name ?? '' })} onClose={close}>
      {target && (
        <div className="modal-body confirm-delete">
          <span className="confirm-delete-icon" aria-hidden="true">
            <Icon name="alert" />
          </span>
          <h3>{t('deletion.title', { name: target.name })}</h3>
          <p>{t(`deletion.what.${target.kind}`)}</p>
          <p className="muted">{t('deletion.noUndo')}</p>
          {mustType && (
            <label>
              {t('deletion.typeName', { name: target.name })}
              <input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" />
            </label>
          )}
          {error && (
            <div role="alert" className="error">
              <p>{error}</p>
              {uses.length > 0 && (
                <ul>
                  {uses.map((text) => (
                    <li key={text}>{use(text)}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="settings-actions">
            <button type="button" className="danger" onClick={remove} disabled={!ready || busy}>
              {busy && <span className="spinner" aria-hidden="true" />}
              {t('deletion.confirm')}
            </button>
            <button type="button" className="secondary" onClick={close}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </Dialog>
  )
}
