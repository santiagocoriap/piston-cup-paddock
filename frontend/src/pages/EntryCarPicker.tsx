import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Dialog } from '../components/Dialog'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'

type Entry = components['schemas']['EntryOut']

/** A button for the driver of an entry (or an admin) to change the car. The list has only the
 * cars of the classes of the season (carIds), or every car when the season has no class. */
export function EntryCarPicker({
  entry,
  carIds,
  onChanged,
}: {
  entry: Entry
  carIds: number[] | null | undefined
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [chosen, setChosen] = useState<number>(entry.car_id)
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const cars = useLoad(() => (open ? api.GET('/api/catalog/cars') : Promise.resolve({ data: undefined })), [open])
  const shown = useMemo(() => {
    const words = query.trim().toLowerCase()
    return (cars.data ?? [])
      .filter((car) => !carIds || carIds.includes(car.id))
      .filter((car) => !words || `${car.name} ${car.brand}`.toLowerCase().includes(words))
  }, [cars.data, carIds, query])

  async function save() {
    setBusy(true)
    const { error: failed } = await api.PUT('/api/entries/{entry_id}/car', {
      params: { path: { entry_id: entry.id } },
      body: { car_id: chosen },
    })
    setBusy(false)
    if (failed) return setError(errorMessage(t, failed))
    setOpen(false)
    onChanged()
  }

  return (
    <>
      <button
        type="button"
        className="secondary small"
        onClick={() => {
          setChosen(entry.car_id)
          setError(null)
          setOpen(true)
        }}
      >
        {t('entryCar.choose')}
      </button>
      <Dialog open={open} title={t('entryCar.title')} onClose={() => setOpen(false)}>
        <h2>{t('entryCar.title')}</h2>
        <p className="muted">{carIds ? t('entryCar.helpClass') : t('entryCar.helpAny')}</p>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('entryCar.search')}
          aria-label={t('entryCar.search')}
        />
        {!cars.data ? (
          <p>{t('app.loading')}</p>
        ) : (
          <fieldset className="skin-choices">
            <legend className="sr-only">{t('entryCar.title')}</legend>
            {shown.map((car) => (
              <label key={car.id} className="skin-choice">
                <input
                  type="radio"
                  className="sr-only"
                  name="car"
                  checked={chosen === car.id}
                  onChange={() => setChosen(car.id)}
                />
                <span className="catalog-media car">
                  {car.has_preview && <img src={`/api/catalog/cars/${car.id}/images/preview`} alt="" loading="lazy" />}
                </span>
                <span className="skin-choice-name">
                  <b title={car.name}>{car.name}</b>
                  {car.brand && <small className="muted">{car.brand}</small>}
                </span>
              </label>
            ))}
          </fieldset>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="settings-actions">
          <button type="button" onClick={save} disabled={busy || chosen === entry.car_id}>
            {t('common.save')}
          </button>
        </div>
      </Dialog>
    </>
  )
}
