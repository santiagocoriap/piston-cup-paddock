import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { errorMessage } from '../lib/errors'
import { Icon } from './Icon'

/** A delete button that asks first. The API answers 409 when something still uses the item,
 * and the button shows that message. The audit log keeps who deleted it. */
export function DeleteButton({
  label,
  confirm,
  run,
  onDone,
  compact = false,
}: {
  label: string
  // The question in the confirm box. Say what goes away with the item.
  confirm: string
  run: () => PromiseLike<{ error?: unknown }>
  onDone: () => void
  // Only the icon, for a table row or a card. The label stays as the name of the button.
  compact?: boolean
}) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove() {
    if (!window.confirm(confirm)) return
    setBusy(true)
    setError(null)
    const { error: apiError } = await run()
    setBusy(false)
    if (apiError) setError(errorMessage(t, apiError))
    else onDone()
  }

  return (
    <>
      <button
        type="button"
        className={compact ? 'icon-button' : 'secondary small danger'}
        aria-label={compact ? label : undefined}
        title={compact ? label : undefined}
        disabled={busy}
        onClick={remove}
      >
        <Icon name="trash" small />
        {!compact && label}
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </>
  )
}
