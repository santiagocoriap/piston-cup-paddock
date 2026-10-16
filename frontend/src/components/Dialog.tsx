import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'

type Props = { open: boolean; title: string; onClose: () => void; children: ReactNode }

/** A modal dialog. It closes with the close button, Escape, or a click outside it. */
export function Dialog({ open, title, onClose, children }: Props) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    // jsdom has no showModal, so the tests use the open attribute.
    if (open && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal()
      else dialog.setAttribute('open', '')
    } else if (!open && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close()
      else dialog.removeAttribute('open')
    }
  }, [open])
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-label={title}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <button type="button" className="dialog-close" aria-label={t('common.close')} onClick={onClose}>
        <Icon name="close" />
      </button>
      {children}
    </dialog>
  )
}
