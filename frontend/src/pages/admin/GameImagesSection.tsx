import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { api, readCookie } from '../../api/client'
import type { components } from '../../api/schema'
import { Icon } from '../../components/Icon'
import { errorMessage } from '../../lib/errors'

type Report = components['schemas']['GameImagesReportOut']

const SCRIPT = 'python tools/pack_game_images.py --needed paddock-needed.json'

function sizeText(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** Track maps and car pictures from the game files: get the list, run the script, upload the ZIP. */
export function GameImagesSection({ onImported }: { onImported: () => void }) {
  const { t } = useTranslation()
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [copied, setCopied] = useState(false)
  const [done, setDone] = useState({ list: false, script: false, zip: false })
  const input = useRef<HTMLInputElement>(null)

  async function download() {
    setError(null)
    const { data, error: failure } = await api.GET('/api/catalog/game-images/needed')
    if (!data) {
      setError(errorMessage(t, failure))
      return
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'paddock-needed.json'
    link.click()
    URL.revokeObjectURL(link.href)
    setDone((old) => ({ ...old, list: true }))
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setReport(null)
    setBusy(true)
    try {
      // A file upload goes with a plain fetch. The typed client sends JSON.
      const response = await fetch('/api/catalog/game-images', {
        method: 'POST',
        body: new FormData(event.currentTarget),
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) setError(errorMessage(t, body))
      else {
        setReport(body as Report)
        setDone((old) => ({ ...old, zip: true }))
        onImported()
      }
    } catch {
      setError(t('errors.generic'))
    } finally {
      setBusy(false)
    }
  }

  function choose(file: File | undefined) {
    setError(null)
    if (file && !file.name.toLowerCase().endsWith('.zip')) {
      setFile(null)
      if (input.current) input.current.value = ''
      setError(t('catalog.images.wrongType'))
      return
    }
    setFile(file ?? null)
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(SCRIPT)
    } catch {
      // Without clipboard access the command stays on screen to copy by hand.
      return
    }
    setCopied(true)
    setDone((old) => ({ ...old, script: true }))
    window.setTimeout(() => setCopied(false), 2000)
  }

  const steps: { key: keyof typeof done; title: string; body: ReactNode }[] = [
    {
      key: 'list',
      title: t('catalog.images.step1Title'),
      body: (
        <>
          <p>{t('catalog.images.step1')}</p>
          <button type="button" className="secondary" onClick={download}>
            <Icon name="download" small />
            {t('catalog.images.download')}
          </button>
        </>
      ),
    },
    {
      key: 'script',
      title: t('catalog.images.step2Title'),
      body: (
        <>
          <p>{t('catalog.images.step2')}</p>
          <div className="command">
            <code className="mono">{SCRIPT}</code>
            <button type="button" className="icon-button" aria-label={t('catalog.images.copy')} title={t('catalog.images.copy')} onClick={copy}>
              <Icon name={copied ? 'check' : 'copy'} small />
            </button>
            <span className="sr-only" role="status">
              {copied ? t('catalog.images.copied') : ''}
            </span>
          </div>
        </>
      ),
    },
    {
      key: 'zip',
      title: t('catalog.images.step3Title'),
      body: (
        <>
          <p>{t('catalog.images.step3')}</p>
          <form className="upload-form" onSubmit={upload} aria-label={t('catalog.images.upload')}>
            <label
              className={dragging ? 'dropzone over' : file ? 'dropzone chosen' : 'dropzone'}
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                const dropped = event.dataTransfer.files
                if (input.current && dropped.length > 0) input.current.files = dropped
                choose(dropped[0])
              }}
            >
              <input
                ref={input}
                className="dropzone-input"
                type="file"
                name="file"
                accept=".zip,application/zip"
                required
                aria-label={t('catalog.images.file')}
                onChange={(event) => choose(event.target.files?.[0])}
              />
              <Icon name={file ? 'check' : 'upload'} />
              <span>{file ? t('catalog.images.chosen', { name: file.name, size: sizeText(file.size) }) : t('catalog.images.dropHere')}</span>
            </label>
            <button type="submit" disabled={busy}>
              {busy ? t('catalog.images.uploading') : t('catalog.images.upload')}
            </button>
          </form>
        </>
      ),
    },
  ]
  const current = steps.findIndex((step) => !done[step.key])

  return (
    <section className="card" aria-labelledby="game-images">
      <h2 id="game-images">{t('catalog.images.title')}</h2>
      <p className="muted">{t('catalog.images.help')}</p>
      <ol className="stepper">
        {steps.map((step, index) => {
          const state = done[step.key] ? 'done' : index === current ? 'current' : 'todo'
          return (
            <li key={step.key} className={`step step-${state}`}>
              <span className="step-marker" aria-hidden="true">
                {state === 'done' ? <Icon name="check" small /> : index + 1}
              </span>
              <div className="step-body">
                <h3>
                  {step.title}
                  {state === 'done' && <span className="sr-only"> · {t('catalog.images.stepDone')}</span>}
                </h3>
                {step.body}
              </div>
            </li>
          )
        })}
      </ol>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {report && (
        <div role="status">
          <p className="success">
            {t('catalog.images.done', { layouts: report.layouts.length, cars: report.cars.length })}
          </p>
          {report.missing_layouts.length + report.missing_cars.length > 0 && (
            <details>
              <summary>
                {t('catalog.images.missing', { count: report.missing_layouts.length + report.missing_cars.length })}
              </summary>
              <ul className="mono">
                {[...report.missing_layouts, ...report.missing_cars].map((key) => (
                  <li key={key}>{key}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
