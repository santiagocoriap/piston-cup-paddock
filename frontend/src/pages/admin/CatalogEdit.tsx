import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { readCookie } from '../../api/client'
import { ActionForm } from '../../components/ActionForm'
import { Dialog } from '../../components/Dialog'
import { RowMenu, type MenuItem } from '../../components/RowMenu'
import { errorMessage } from '../../lib/errors'

export type ImageKind = 'outline' | 'preview' | 'badge'

/** One field of the edit dialog. "tags" is a text of words with commas between them. */
export type EditField = {
  name: string
  label: string
  kind: 'text' | 'number' | 'textarea' | 'select' | 'url' | 'tags'
  value: string | number | null | string[]
  required?: boolean
  min?: number
  max?: number
  step?: string
  options?: [string, string][]
}

/** The request body from the form: an empty number is null, tags become a list. */
function bodyOf(fields: EditField[], form: FormData): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  for (const field of fields) {
    const raw = String(form.get(field.name) ?? '').trim()
    if (field.kind === 'number') body[field.name] = raw === '' ? null : Number(raw)
    else if (field.kind === 'tags') body[field.name] = raw.split(',').map((tag) => tag.trim()).filter(Boolean)
    else body[field.name] = raw
  }
  return body
}

function FieldInput({ field }: { field: EditField }) {
  const value = Array.isArray(field.value) ? field.value.join(', ') : (field.value ?? '')
  const wide = field.kind === 'textarea' || field.kind === 'tags'
  return (
    <label className={wide ? 'wide' : undefined}>
      {field.label}
      {field.kind === 'textarea' ? (
        <textarea name={field.name} defaultValue={String(value)} rows={4} maxLength={field.max} />
      ) : field.kind === 'select' ? (
        <select name={field.name} defaultValue={String(value)}>
          {field.options?.map(([option, label]) => (
            <option key={option} value={option}>
              {label}
            </option>
          ))}
        </select>
      ) : (
        <input
          name={field.name}
          type={field.kind === 'number' ? 'number' : field.kind === 'url' ? 'url' : 'text'}
          defaultValue={String(value)}
          required={field.required}
          min={field.kind === 'number' ? field.min : undefined}
          max={field.kind === 'number' ? field.max : undefined}
          maxLength={field.kind === 'number' ? undefined : field.max}
          step={field.step}
        />
      )}
    </label>
  )
}

/** A catalog item: a track, a layout, or a car. "base" is its API path, for example
 * "/api/catalog/cars/4". "images" lists its picture kinds, and if each one is set. */
type Props = {
  name: string
  /** A track also has a country. With it, the dialog edits the name and the country. */
  country?: string
  /** The fields of the edit dialog. Without them, the dialog edits the name (and the country). */
  fields?: EditField[]
  base: string
  images?: { kind: ImageKind; set: boolean }[]
  onChange: () => void
}

/** Send a request with the CSRF token. A picture goes as a form, a name as JSON. */
async function send(method: string, url: string, body?: FormData | object) {
  const json = body !== undefined && !(body instanceof FormData)
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '', ...(json ? { 'Content-Type': 'application/json' } : {}) },
    body: json ? JSON.stringify(body) : (body as FormData | undefined),
  })
  return response.ok ? undefined : ((await response.json().catch(() => null)) ?? { detail: 'generic' })
}

/** The edit menu of a catalog item: change the name, and upload or remove each picture. */
export function CatalogEdit({ name, country, fields, base, images = [], onChange }: Props) {
  const { t } = useTranslation()
  const [renaming, setRenaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)
  const uploadKind = useRef<ImageKind>('preview')

  function pick(kind: ImageKind) {
    uploadKind.current = kind
    file.current?.click()
  }

  async function upload(chosen: File | undefined) {
    if (!chosen) return
    setError(null)
    const form = new FormData()
    form.append('file', chosen)
    const problem = await send('POST', `${base}/images/${uploadKind.current}`, form)
    if (file.current) file.current.value = ''
    if (problem) setError(errorMessage(t, problem))
    else onChange()
  }

  async function remove(kind: ImageKind) {
    if (!window.confirm(t('catalogEdit.confirmRemove'))) return
    setError(null)
    const problem = await send('DELETE', `${base}/images/${kind}`)
    if (problem) setError(errorMessage(t, problem))
    else onChange()
  }

  const editLabel = t(fields ? 'catalogEdit.editFacts' : country === undefined ? 'catalogEdit.rename' : 'catalogEdit.editTrack')
  const editFields: EditField[] = fields ?? [
    { name: 'name', label: t('catalogEdit.name'), kind: 'text', value: name, required: true, max: 200 },
    ...(country === undefined
      ? []
      : [{ name: 'country', label: t('catalogEdit.country'), kind: 'text' as const, value: country, max: 100 }]),
  ]
  const items: MenuItem[] = [
    { label: editLabel, onSelect: () => setRenaming(true) },
    ...images.flatMap(({ kind, set }) => [
      { label: t(`catalogEdit.upload.${kind}`), onSelect: () => pick(kind) },
      ...(set ? [{ label: t(`catalogEdit.remove.${kind}`), onSelect: () => remove(kind) }] : []),
    ]),
  ]

  return (
    <span className="catalog-edit">
      <RowMenu label={t('catalogEdit.menu', { name })} items={items} />
      <input
        ref={file}
        className="sr-only"
        type="file"
        accept="image/png,image/jpeg"
        tabIndex={-1}
        aria-label={t('catalogEdit.file', { name })}
        onChange={(event) => upload(event.target.files?.[0])}
      />
      {error && (
        <span role="alert" className="error">
          {error}
        </span>
      )}
      <Dialog open={renaming} title={editLabel} onClose={() => setRenaming(false)}>
        {renaming && (
          <ActionForm
            title={editLabel}
            submitLabel={t('common.save')}
            onDone={() => setRenaming(false)}
            onSubmit={async (form) => {
              const problem = await send('PATCH', base, bodyOf(editFields, form))
              if (!problem) onChange()
              return problem
            }}
          >
            {editFields.map((field) => (
              <FieldInput key={field.name} field={field} />
            ))}
          </ActionForm>
        )}
      </Dialog>
    </span>
  )
}

/** The empty picture box, with a button that uploads the first picture. */
export function MissingImage({ base, kind, onChange }: { base: string; kind: ImageKind; onChange: () => void }) {
  const { t } = useTranslation()
  const file = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  return (
    <span className="catalog-missing-box">
      <span className="catalog-missing">{t('catalog.noImage')}</span>
      <button type="button" className="secondary small" onClick={() => file.current?.click()}>
        {t(`catalogEdit.upload.${kind}`)}
      </button>
      <span className="muted catalog-hint">{t('catalogEdit.help')}</span>
      <input
        ref={file}
        className="sr-only"
        type="file"
        accept="image/png,image/jpeg"
        tabIndex={-1}
        aria-label={t(`catalogEdit.upload.${kind}`)}
        onChange={async (event) => {
          const chosen = event.target.files?.[0]
          if (!chosen) return
          const form = new FormData()
          form.append('file', chosen)
          const problem = await send('POST', `${base}/images/${kind}`, form)
          event.target.value = ''
          if (problem) setError(errorMessage(t, problem))
          else onChange()
        }}
      />
      {error && (
        <span role="alert" className="error">
          {error}
        </span>
      )}
    </span>
  )
}
