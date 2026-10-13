import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, readCookie } from '../../api/client'
import type { components } from '../../api/schema'
import { errorMessage } from '../../lib/errors'

type Report = components['schemas']['GameImagesReportOut']

const SCRIPT = 'python tools/pack_game_images.py --needed paddock-needed.json'

/** Track maps and car pictures from the game files: get the list, run the script, upload the ZIP. */
export function GameImagesSection({ onImported }: { onImported: () => void }) {
  const { t } = useTranslation()
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
        onImported()
      }
    } catch {
      setError(t('errors.generic'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card game-images" aria-labelledby="game-images">
      <h2 id="game-images">{t('catalog.images.title')}</h2>
      <p className="muted">{t('catalog.images.help')}</p>
      <ol className="game-steps">
        <li>
          <p>{t('catalog.images.step1')}</p>
          <button type="button" className="secondary" onClick={download}>
            {t('catalog.images.download')}
          </button>
        </li>
        <li>
          <p>{t('catalog.images.step2')}</p>
          <code className="mono">{SCRIPT}</code>
        </li>
        <li>
          <p>{t('catalog.images.step3')}</p>
          <form className="upload" onSubmit={upload} aria-label={t('catalog.images.upload')}>
            <label>
              {t('catalog.images.file')}
              <input type="file" name="file" accept=".zip,application/zip" required />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? t('catalog.images.uploading') : t('catalog.images.upload')}
            </button>
          </form>
        </li>
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
