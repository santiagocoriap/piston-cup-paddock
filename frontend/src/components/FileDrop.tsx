import { useRef, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'

type Props = { label: string; name: string; accept: string; multiple?: boolean; required?: boolean }

/** A file field as a drop area. A click opens the file picker. A dropped file goes into the same
 * field, so the form sends it as usual. */
export function FileDrop({ label, name, accept, multiple = false, required = false }: Props) {
  const { t } = useTranslation()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [names, setNames] = useState<string[]>([])

  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setOver(false)
    const field = input.current
    if (!field || event.dataTransfer.files.length === 0) return
    field.files = event.dataTransfer.files
    setNames([...field.files].map((file) => file.name))
  }

  return (
    <label
      className={over ? 'file-drop over' : 'file-drop'}
      onDragOver={(event) => {
        event.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
    >
      <span className="file-drop-label">{label}</span>
      <span className="file-drop-box">
        <Icon name="upload" />
        <span>
          {names.length > 0 ? (
            <b>{names.join(', ')}</b>
          ) : (
            <>
              <b>{t('fileDrop.choose')}</b> {t('fileDrop.orDrop')}
            </>
          )}
        </span>
      </span>
      <input
        ref={input}
        className="sr-only"
        aria-label={label}
        name={name}
        type="file"
        accept={accept}
        multiple={multiple}
        required={required}
        onChange={(event) => setNames([...(event.target.files ?? [])].map((file) => file.name))}
      />
    </label>
  )
}
