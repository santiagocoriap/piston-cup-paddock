import { useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { errorMessage } from '../lib/errors'

type Props = {
  title: string
  submitLabel: string
  /** Send the form. Return the API error, or undefined when the request worked. */
  onSubmit: (form: FormData) => Promise<unknown>
  children: ReactNode
}

/** A form that shows the API error, and clears its fields after a success. */
export function ActionForm({ title, submitLabel, onSubmit, children }: Props) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const element = event.currentTarget
    setBusy(true)
    setError(null)
    const apiError = await onSubmit(new FormData(element))
    setBusy(false)
    if (apiError === undefined) element.reset()
    else setError(errorMessage(t, apiError))
  }

  return (
    <form className="card" onSubmit={submit} aria-label={title}>
      <h3>{title}</h3>
      {children}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy}>
        {submitLabel}
      </button>
    </form>
  )
}
