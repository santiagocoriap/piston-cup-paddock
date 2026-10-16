import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { errorMessage } from '../lib/errors'

type Step = { title: string; content: ReactNode }

type Props = {
  title: string
  steps: Step[]
  submitLabel: string
  /** Send the form. Return the API error, or undefined when the request worked. */
  onSubmit: (form: FormData) => Promise<unknown>
  /** Runs after a success, for example to close the dialog that holds the form. */
  onDone?: () => void
}

/** A long form in steps. All the steps stay in one form, so the send button sends every field.
 * "Siguiente" checks the fields of the step first. The send button works on every step,
 * because the later steps have good defaults. */
export function StepForm({ title, steps, submitLabel, onSubmit, onDone }: Props) {
  const { t } = useTranslation()
  const [step, setStep] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const form = useRef<HTMLFormElement>(null)

  function fields(index: number) {
    const fieldset = form.current?.querySelectorAll('fieldset.form-step')[index]
    return [...(fieldset?.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select, textarea') ?? [])]
  }

  /** Shows the first step from "from" to "to" (not included) with a wrong field. Returns false when it finds one. */
  function check(from: number, to: number): boolean {
    for (let index = from; index < to; index++) {
      const wrong = fields(index).find((field) => !field.checkValidity())
      if (wrong) {
        setStep(index)
        // The browser can show the message only after the step is visible.
        window.setTimeout(() => wrong.reportValidity())
        return false
      }
    }
    return true
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!check(0, steps.length)) return
    const element = event.currentTarget
    setBusy(true)
    setError(null)
    const apiError = await onSubmit(new FormData(element))
    setBusy(false)
    if (apiError === undefined) {
      element.reset()
      setStep(0)
      onDone?.()
    } else setError(errorMessage(t, apiError))
  }

  return (
    <form ref={form} className="card" onSubmit={submit} aria-label={title} noValidate>
      <h3>{title}</h3>
      <ol className="step-rail">
        {steps.map((item, index) => (
          <li key={item.title}>
            <button
              type="button"
              className={index === step ? 'step-tab current' : index < step ? 'step-tab done' : 'step-tab'}
              aria-current={index === step ? 'step' : undefined}
              onClick={() => {
                if (index <= step || check(step, index)) setStep(index)
              }}
            >
              <span className="step-number" aria-hidden="true">
                {index + 1}
              </span>
              {item.title}
            </button>
          </li>
        ))}
      </ol>
      {steps.map((item, index) => (
        <fieldset key={item.title} className="form-step" hidden={index !== step}>
          <legend className="sr-only">{item.title}</legend>
          {item.content}
        </fieldset>
      ))}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="step-actions">
        <span className="muted step-count">{t('common.stepOf', { current: step + 1, total: steps.length })}</span>
        {step > 0 && (
          <button type="button" className="secondary" onClick={() => setStep(step - 1)}>
            {t('common.back')}
          </button>
        )}
        {step < steps.length - 1 && (
          <button type="button" className="secondary" onClick={() => check(step, step + 1) && setStep(step + 1)}>
            {t('common.next')}
          </button>
        )}
        <button type="submit" disabled={busy}>
          {submitLabel}
        </button>
      </div>
    </form>
  )
}
