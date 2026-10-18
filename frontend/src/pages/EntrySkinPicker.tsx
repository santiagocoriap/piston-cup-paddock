import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Dialog } from '../components/Dialog'
import { errorMessage } from '../lib/errors'

type Entry = components['schemas']['EntryOut']
type Skin = components['schemas']['EntrySkinOut']

/** The skin of an entry, and for the driver of the entry (or an admin) a button to choose it.
 * "Auto" leaves the choice to the server. The skins are the ones of the car of the entry. */
export function EntrySkinPicker({ entry, canChange, onChanged }: { entry: Entry; canChange: boolean; onChanged: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [skins, setSkins] = useState<Skin[] | null>(null)
  const [chosen, setChosen] = useState<number | null>(entry.skin_id ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function show() {
    setChosen(entry.skin_id ?? null)
    setError(null)
    setOpen(true)
    const { data } = await api.GET('/api/entries/{entry_id}/skins', { params: { path: { entry_id: entry.id } } })
    setSkins(data ?? [])
  }

  async function save() {
    setBusy(true)
    const { error: failed } = await api.PUT('/api/entries/{entry_id}/skin', {
      params: { path: { entry_id: entry.id } },
      body: { skin_id: chosen },
    })
    setBusy(false)
    if (failed) return setError(errorMessage(t, failed))
    setOpen(false)
    onChanged()
  }

  const current = entry.skin_name || t('entrySkin.auto')
  return (
    <>
      <span className="muted entry-skin" title={t('entrySkin.current', { name: current })}>
        {t('entrySkin.label')}: {current}
      </span>
      {canChange && (
        <button type="button" className="secondary small" onClick={() => void show()}>
          {t('entrySkin.choose')}
        </button>
      )}
      <Dialog open={open} title={t('entrySkin.title', { car: entry.car_name })} onClose={() => setOpen(false)}>
        <h2>{t('entrySkin.title', { car: entry.car_name })}</h2>
        <p className="muted">{t('entrySkin.help')}</p>
        {skins === null ? (
          <p>{t('app.loading')}</p>
        ) : (
          <fieldset className="skin-choices">
            <legend className="sr-only">{t('entrySkin.label')}</legend>
            <label className="skin-choice">
              <input type="radio" className="sr-only" name="skin" checked={chosen === null} onChange={() => setChosen(null)} />
              <span className="catalog-media car skin-choice-auto">{t('entrySkin.auto')}</span>
              <span className="skin-choice-name">
                <b>{t('entrySkin.auto')}</b>
                <small className="muted">{t('entrySkin.autoHelp')}</small>
              </span>
            </label>
            {skins.map((skin) => (
              <label key={skin.id} className="skin-choice">
                <input type="radio" className="sr-only" name="skin" checked={chosen === skin.id} onChange={() => setChosen(skin.id)} />
                <span className="catalog-media car">
                  {skin.has_preview && <img src={`/api/catalog/skins/${skin.id}/preview`} alt="" loading="lazy" />}
                </span>
                <span className="skin-choice-name">
                  <b title={skin.name || skin.key}>{skin.name || skin.key}</b>
                  {(skin.number || skin.team) && (
                    <small className="muted">{[skin.number && `#${skin.number}`, skin.team].filter(Boolean).join(' · ')}</small>
                  )}
                </span>
              </label>
            ))}
          </fieldset>
        )}
        {error && <p role="alert">{error}</p>}
        <div className="skin-actions">
          <button type="button" disabled={busy || skins === null} onClick={() => void save()}>
            {t('common.save')}
          </button>
        </div>
      </Dialog>
    </>
  )
}
