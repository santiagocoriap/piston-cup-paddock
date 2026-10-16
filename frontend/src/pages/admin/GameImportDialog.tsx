import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { readCookie } from '../../api/client'
import { Dialog } from '../../components/Dialog'
import { Icon } from '../../components/Icon'
import { errorMessage } from '../../lib/errors'
import {
  contentFolder,
  fromFileList,
  packSelection,
  scanCars,
  scanTracks,
  type DirHandle,
  type GameCar,
  type GameTrack,
} from '../../lib/gameFolder'

type Kind = 'cars' | 'tracks'
type Picker = (options: { mode: 'read' }) => Promise<DirHandle>
type Result = { new_tracks: string[]; new_layouts: string[]; new_cars: string[] }

// The app sends the chosen items in parts, so one request stays small.
const BATCH = 10

/** "Importar desde el juego": pick the assettocorsa folder, tick the cars and the tracks, and
 * the app adds them with their pictures and data. The browser reads the folder: the app on the
 * server never sees the PC. */
export function GameImportDialog({
  open,
  onClose,
  onImported,
  knownCars,
  knownTracks,
}: {
  open: boolean
  onClose: () => void
  onImported: () => void
  knownCars: string[]
  knownTracks: string[]
}) {
  const { t } = useTranslation()
  const [cars, setCars] = useState<GameCar[] | null>(null)
  const [tracks, setTracks] = useState<GameTrack[] | null>(null)
  const [scanned, setScanned] = useState(0)
  const [kind, setKind] = useState<Kind>('cars')
  const [query, setQuery] = useState('')
  const [onlyNew, setOnlyNew] = useState(true)
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [progress, setProgress] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const known = useMemo(
    () => ({ cars: new Set(knownCars.map((k) => k.toLowerCase())), tracks: new Set(knownTracks.map((k) => k.toLowerCase())) }),
    [knownCars, knownTracks],
  )
  const picker = (window as unknown as { showDirectoryPicker?: Picker }).showDirectoryPicker

  const folderInput = useRef<HTMLInputElement>(null)

  async function pick() {
    setError(null)
    if (!picker) {
      // Firefox: a file input that takes a whole folder.
      folderInput.current?.click()
      return
    }
    let picked: DirHandle
    try {
      picked = await picker({ mode: 'read' })
    } catch {
      return // The admin closed the picker.
    }
    await scan(picked)
  }

  async function scan(picked: DirHandle | null) {
    setError(null)
    const content = picked ? await contentFolder(picked) : null
    if (!content) {
      setProgress(null)
      setError(t('gameImport.wrongFolder'))
      return
    }
    setScanned(0)
    setProgress(t('gameImport.reading'))
    const foundCars = await scanCars(content, setScanned)
    const foundTracks = await scanTracks(content, (n) => setScanned(foundCars.length + n))
    setCars(foundCars)
    setTracks(foundTracks)
    setChosen(new Set())
    setProgress(null)
  }

  const items = useMemo(() => {
    const isNew = (k: Kind, key: string) => !known[k].has(key.toLowerCase())
    const rows =
      kind === 'cars'
        ? (cars ?? []).map((c) => ({ id: `cars:${c.key}`, key: c.key, name: c.name, extra: c.brand, isNew: isNew('cars', c.key) }))
        : (tracks ?? []).map((tr) => ({
            id: `tracks:${tr.key}`,
            key: tr.key,
            name: tr.name,
            extra: t('gameImport.layouts', { count: tr.layouts.length }),
            isNew: isNew('tracks', tr.key),
          }))
    const words = query.trim().toLowerCase()
    return rows.filter(
      (row) => (!onlyNew || row.isNew) && (!words || `${row.name} ${row.key}`.toLowerCase().includes(words)),
    )
  }, [cars, tracks, kind, query, onlyNew, known, t])

  const toggle = (id: string) =>
    setChosen((old) => {
      const next = new Set(old)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const allShown = items.length > 0 && items.every((row) => chosen.has(row.id))
  const toggleShown = () =>
    setChosen((old) => {
      const next = new Set(old)
      for (const row of items) {
        if (allShown) next.delete(row.id)
        else next.add(row.id)
      }
      return next
    })

  async function importChosen() {
    setError(null)
    const pickedCars = (cars ?? []).filter((c) => chosen.has(`cars:${c.key}`))
    const pickedTracks = (tracks ?? []).filter((tr) => chosen.has(`tracks:${tr.key}`))
    const queue = [
      ...pickedCars.map((car) => ({ car, track: null })),
      ...pickedTracks.map((track) => ({ car: null, track })),
    ]
    const total = queue.length
    const all: Result = { new_tracks: [], new_layouts: [], new_cars: [] }
    let done = 0
    let failed = false
    try {
      for (let i = 0; i < total; i += BATCH) {
        const part = queue.slice(i, i + BATCH)
        const partCars = part.flatMap((item) => (item.car ? [item.car] : []))
        const partTracks = part.flatMap((item) => (item.track ? [item.track] : []))
        setProgress(t('gameImport.sending', { done, total }))
        const form = new FormData()
        form.append('file', await packSelection(partCars, partTracks), 'game.zip')
        const response = await fetch('/api/catalog/game-import', {
          method: 'POST',
          body: form,
          credentials: 'same-origin',
          headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
        })
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          setError(errorMessage(t, body))
          failed = true
          break
        }
        const added = body as Result
        all.new_tracks.push(...added.new_tracks)
        all.new_layouts.push(...added.new_layouts)
        all.new_cars.push(...added.new_cars)
        done += partCars.length + partTracks.length
      }
    } finally {
      setProgress(null)
    }
    // After an error, the items before it are in the catalog: show them too.
    if (!failed || done > 0) setResult(all)
    if (!failed) setChosen(new Set())
    onImported()
  }

  function close() {
    setResult(null)
    setError(null)
    onClose()
  }

  return (
    <Dialog open={open} title={t('gameImport.title')} onClose={close}>
      <div className="modal-body game-import">
        <h3>{t('gameImport.title')}</h3>
        <input
          ref={(element) => {
            folderInput.current = element
            // React has no prop for these attributes.
            element?.setAttribute('webkitdirectory', '')
            element?.setAttribute('directory', '')
          }}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            // Copy the files first: in Firefox, the clear below also empties the FileList.
            const files = Array.from(event.target.files ?? [])
            event.target.value = ''
            if (files.length === 0) {
              setError(t('gameImport.noFiles'))
              return
            }
            setProgress(t('gameImport.reading'))
            // Let the page show the message before the long work.
            window.setTimeout(() => void scan(fromFileList(files)), 0)
          }}
        />
        {!cars && !progress && (
          <>
            <p>{t('gameImport.help')}</p>
            <button type="button" onClick={pick}>
              <Icon name="upload" small />
              {t('gameImport.pick')}
            </button>
          </>
        )}
        {progress && (
          <p role="status" className="muted">
            <span className="spinner" aria-hidden="true" /> {progress} {!cars && t('gameImport.found', { count: scanned })}
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {result && (
          <p role="status" className="success">
            {t('gameImport.done', {
              cars: result.new_cars.length,
              tracks: result.new_tracks.length,
              layouts: result.new_layouts.length,
            })}
          </p>
        )}
        {cars && tracks && !progress && (
          <>
            <div className="game-import-tabs" role="tablist" aria-label={t('gameImport.title')}>
              {(['cars', 'tracks'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={kind === k}
                  className={kind === k ? 'active' : undefined}
                  onClick={() => setKind(k)}
                >
                  {t(`gameImport.${k}`, { count: (k === 'cars' ? cars : tracks).length })}
                </button>
              ))}
            </div>
            <div className="game-import-filters">
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('gameImport.search')}
                aria-label={t('gameImport.search')}
              />
              <label className="check">
                <input type="checkbox" checked={onlyNew} onChange={(e) => setOnlyNew(e.target.checked)} />
                {t('gameImport.onlyNew')}
              </label>
              <label className="check">
                <input type="checkbox" checked={allShown} onChange={toggleShown} disabled={items.length === 0} />
                {t('gameImport.allShown', { count: items.length })}
              </label>
            </div>
            <ul className="game-import-list">
              {items.map((row) => (
                <li key={row.id}>
                  <label className="check">
                    <input type="checkbox" checked={chosen.has(row.id)} onChange={() => toggle(row.id)} />
                    <span className="game-import-name">
                      <b>{row.name}</b>
                      <span className="muted mono">{row.key}</span>
                      {row.extra && <span className="muted">{row.extra}</span>}
                    </span>
                    {!row.isNew && <span className="badge">{t('gameImport.inCatalog')}</span>}
                  </label>
                </li>
              ))}
              {items.length === 0 && <li className="muted">{t('gameImport.none')}</li>}
            </ul>
            <div className="settings-actions">
              <button type="button" onClick={importChosen} disabled={chosen.size === 0}>
                {t('gameImport.import', { count: chosen.size })}
              </button>
              <button type="button" className="secondary" onClick={pick}>
                {t('gameImport.pickAgain')}
              </button>
            </div>
          </>
        )}
      </div>
    </Dialog>
  )
}
