import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Collectors = components['schemas']['CollectorsOut']
type CollectorFile = components['schemas']['CollectorFileOut']

/** Server collector keys and the files they sent. The key shows one time only. */
export function CollectorsSection({ championshipId }: { championshipId: number }) {
  const { t, i18n } = useTranslation()
  const path = { championship_id: championshipId }
  const load = useLoad(
    () => api.GET('/api/championships/{championship_id}/collectors', { params: { path } }),
    [championshipId],
  )
  const [override, setOverride] = useState<Collectors | null>(null)
  const [newKey, setNewKey] = useState<NewKey | null>(null)
  const data = override ?? load.data
  if (!data) return null

  async function revoke(id: number) {
    const { data: next } = await api.POST('/api/collectors/{collector_id}/revoke', {
      params: { path: { collector_id: id } },
    })
    if (next) setOverride(next)
  }

  return (
    <div className="card" role="region" aria-label={t('collectors.title')}>
      <h3>{t('collectors.title')}</h3>
      <p className="muted">{t('collectors.help')}</p>
      {data.collectors.length === 0 && <p>{t('collectors.none')}</p>}
      <ul className="list">
        {data.collectors.map((collector) => (
          <li key={collector.id}>
            <strong>{collector.name}</strong>
            {collector.revoked && <span className="badge">{t('collectors.revoked')}</span>} ·{' '}
            {collector.last_seen_at
              ? t('collectors.lastSeen', { date: formatDateTime(collector.last_seen_at, i18n.language) })
              : t('collectors.neverSeen')}{' '}
            · {t('collectors.counts', { files: collector.files, events: collector.events })}
            {!collector.revoked && (
              <button type="button" className="link-button" onClick={() => revoke(collector.id)}>
                {t('collectors.revoke')}
              </button>
            )}
          </li>
        ))}
      </ul>
      {newKey && <KeyBox newKey={newKey} />}
      <ActionForm
        title={t('collectors.create')}
        submitLabel={t('collectors.createButton')}
        onSubmit={async (form) => {
          const { data: created, error } = await api.POST('/api/championships/{championship_id}/collectors', {
            params: { path },
            body: { name: String(form.get('name')) },
          })
          if (created) {
            setNewKey({ id: created.id, name: created.name, key: created.key })
            setOverride(null)
            load.reload()
          }
          return error
        }}
      >
        <label>
          {t('collectors.name')}
          <input name="name" required maxLength={60} />
        </label>
      </ActionForm>
      {data.files.length > 0 && (
        <>
          <h4>{t('collectors.files')}</h4>
          <ul className="list">
            {data.files.map((file) => (
              <FileRow key={file.id} file={file} data={data} onChange={setOverride} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

type NewKey = { id: number; name: string; key: string }

/** The new key, one time only, and "Descargar colector": a zip with the Windows program and a
 * collector.ini with this key. The app keeps only a hash of the key, so the zip is possible now
 * only. */
function KeyBox({ newKey }: { newKey: NewKey }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function download() {
    setError(null)
    setBusy(true)
    const { data, error } = await api.POST('/api/collectors/{collector_id}/package', {
      params: { path: { collector_id: newKey.id } },
      body: { key: newKey.key },
      parseAs: 'blob',
    })
    setBusy(false)
    if (!data) {
      setError(errorMessage(t, error))
      return
    }
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = 'paddock-collector.zip'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="link-box" role="status">
      <p>
        <strong>{t('collectors.keyFor', { name: newKey.name })}</strong> {t('collectors.keyOnce')}
      </p>
      <input readOnly value={newKey.key} onFocus={(e) => e.target.select()} aria-label={t('collectors.key')} />
      <div className="key-download">
        <button type="button" onClick={download} disabled={busy}>
          {busy && <span className="spinner" aria-hidden="true" />}
          {t('collectors.download')}
        </button>
        <small className="muted">{t('collectors.downloadHelp')}</small>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}

function FileRow({
  file,
  data,
  onChange,
}: {
  file: CollectorFile
  data: Collectors
  onChange: (next: Collectors) => void
}) {
  const { t, i18n } = useTranslation()
  const [roundId, setRoundId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const round = data.rounds.find((r) => r.id === file.round_id)

  async function assign() {
    setError(null)
    const { data: next, error } = await api.POST('/api/collector-files/{file_id}/assign', {
      params: { path: { file_id: file.id } },
      body: { round_id: Number(roundId) },
    })
    if (next) onChange(next)
    else setError(errorMessage(t, error))
  }

  return (
    <li>
      {file.filename} · {t(`collectors.kind.${file.kind}`)} · {formatDateTime(file.session_time, i18n.language)} ·{' '}
      <span className={file.status === 'assigned' ? undefined : 'warning'}>{t(`collectors.status.${file.status}`)}</span>
      {round && ` · ${round.season_name} R${round.number} ${round.track_name}`}
      {file.error && ` · ${t(`collectors.errors.${file.error}`, { defaultValue: file.error })}`}
      {file.status === 'unmatched' && (
        <span className="inline">
          {' '}
          <select value={roundId} onChange={(e) => setRoundId(e.target.value)} aria-label={t('collectors.chooseRound', { name: file.filename })}>
            <option value="">{t('common.select')}</option>
            {data.rounds.map((r) => (
              <option key={r.id} value={r.id}>
                {r.season_name} R{r.number} · {r.track_name} · {formatDateTime(r.scheduled_at, i18n.language)}
              </option>
            ))}
          </select>
          <button type="button" disabled={!roundId} onClick={assign}>
            {t('collectors.assign')}
          </button>
        </span>
      )}
      {error && (
        <span role="alert" className="error">
          {' '}
          {error}
        </span>
      )}
    </li>
  )
}
