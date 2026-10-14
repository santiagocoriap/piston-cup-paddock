import { useId, useState, type InputHTMLAttributes, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'

type Props = { label: string } & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>

/** A password input with a button that shows the text, and a warning when Caps Lock is on. */
export function PasswordField({ label, onChange, ...input }: Props) {
  const { t } = useTranslation()
  const id = useId()
  const [visible, setVisible] = useState(false)
  const [capsLock, setCapsLock] = useState(false)

  function readCaps(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState?.('CapsLock') ?? false)
  }

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <span className="input-icon">
        <Icon name="lock" small />
        <input id={id} type={visible ? 'text' : 'password'} onKeyUp={readCaps} onKeyDown={readCaps} onChange={onChange} {...input} />
        <button
          type="button"
          className="reveal"
          aria-label={visible ? t('auth.hide') : t('auth.show')}
          aria-pressed={visible}
          aria-controls={id}
          onClick={() => setVisible((value) => !value)}
        >
          <Icon name={visible ? 'eyeOff' : 'eye'} small />
        </button>
      </span>
      {capsLock && (
        <span className="caps-warning" role="status">
          <Icon name="alert" small />
          {t('auth.capsLock')}
        </span>
      )}
    </div>
  )
}
