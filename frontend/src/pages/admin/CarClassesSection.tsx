import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { DangerMenu } from '../../components/DangerMenu'
import { Dialog } from '../../components/Dialog'
import { DualPicker, type PickItem } from '../../components/DualPicker'
import { CatalogEdit } from './CatalogEdit'
import { CarStats } from './CatalogFacts'
import { carFields } from './catalogFields'

type CarClass = components['schemas']['CarClassOut']
type Car = components['schemas']['CarOut']

/** Car classes and their cars. A change keeps the old rows in the history.
 * onSaved: a class changed. onCarsChanged: a car changed (its name, picture, or a delete). */
export function CarClassesSection({
  cars,
  classes,
  onSaved,
  onCarsChanged,
}: {
  cars: Car[]
  classes: CarClass[]
  onSaved: () => void
  onCarsChanged: () => void
}) {
  const { t } = useTranslation()
  return (
    <section aria-label={t('classes.title')} className="class-list">
      {classes.map((item) => (
        <ClassCard key={item.id} item={item} cars={cars} onSaved={onSaved} onCarsChanged={onCarsChanged} />
      ))}
    </section>
  )
}

function ClassCard({
  item,
  cars,
  onSaved,
  onCarsChanged,
}: {
  item: CarClass
  cars: Car[]
  onSaved: () => void
  onCarsChanged: () => void
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [picked, setPicked] = useState(item.car_ids)
  const [error, setError] = useState<string | null>(null)
  const pickItems: PickItem[] = cars.map((car) => ({
    id: car.id,
    title: car.name,
    subtitle: car.brand,
    origin: { key: car.source, label: t(`carDetail.source.${car.source}`) },
    tags: car.tags ?? [],
    image: car.has_preview ? `/api/catalog/cars/${car.id}/images/preview` : null,
    details: <CarStats car={car} />,
  }))
  const members = cars.filter((c) => item.car_ids.includes(c.id))

  async function saveCars(carIds: number[], reason: string) {
    const { error } = await api.PUT('/api/catalog/classes/{class_id}/cars', {
      params: { path: { class_id: item.id } },
      body: { car_ids: carIds, reason },
    })
    if (!error) onSaved()
    return error
  }

  async function removeCar(car: Car) {
    if (!window.confirm(t('classes.confirmRemove', { car: car.name, name: item.name }))) return
    setError(null)
    const problem = await saveCars(
      item.car_ids.filter((id) => id !== car.id),
      '',
    )
    if (problem) setError(t('errors.generic'))
  }

  return (
    <div className="card class-card">
      <div className="class-head">
        <h3>
          {item.name} <span className="muted class-count">{t('classes.carCount', { count: members.length })}</span>
        </h3>
        <DangerMenu
          target={{ kind: 'car_class', id: item.id, name: item.name }}
          onDeleted={onSaved}
          items={[
            { label: t('classes.rename'), onSelect: () => setRenaming(true) },
            {
              label: t('classes.editCars'),
              onSelect: () => {
                setPicked(item.car_ids)
                setEditing(true)
              },
            },
          ]}
        />
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {members.length > 0 ? (
        <ul className="catalog-grid class-cars">
          {members.map((car) => (
            <ClassCar key={car.id} car={car} onChange={onCarsChanged} onRemove={() => removeCar(car)} />
          ))}
        </ul>
      ) : (
        <p className="muted">{t('classes.noCars')}</p>
      )}
      {editing && (
        <ActionForm
          title={t('classes.carsOf', { name: item.name })}
          submitLabel={t('common.save')}
          onDone={() => setEditing(false)}
          onSubmit={async (form) => {
            const problem = await saveCars(form.getAll('car_ids').map(Number), String(form.get('reason') ?? ''))
            if (!problem) setEditing(false)
            return problem
          }}
        >
          <DualPicker name="car_ids" items={pickItems} value={picked} onChange={setPicked} searchLabel={t('classes.search')} />
          <label>
            {t('classes.reason')}
            <input name="reason" maxLength={300} />
          </label>
        </ActionForm>
      )}
      <Dialog open={renaming} title={t('classes.rename')} onClose={() => setRenaming(false)}>
        {renaming && (
          <ActionForm
            title={t('classes.rename')}
            submitLabel={t('common.save')}
            onDone={() => setRenaming(false)}
            onSubmit={async (form) => {
              const { error } = await api.PATCH('/api/catalog/classes/{class_id}', {
                params: { path: { class_id: item.id } },
                body: { name: String(form.get('name') ?? '') },
              })
              if (!error) {
                setRenaming(false)
                onSaved()
              }
              return error
            }}
          >
            <label>
              {t('classes.name')}
              <input name="name" defaultValue={item.name} required maxLength={60} />
            </label>
          </ActionForm>
        )}
      </Dialog>
      {item.history.some((h) => h.valid_to) && (
        <details>
          <summary>{t('classes.history')}</summary>
          <ul>
            {item.history.map((h, index) => (
              <li key={index}>
                {h.car_name}: {h.valid_from} → {h.valid_to ?? t('classes.today')}
                {h.reason && ` (${h.reason})`}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/** A small card of a car in a class: the picture, the name, and the menu of the car. */
function ClassCar({ car, onChange, onRemove }: { car: Car; onChange: () => void; onRemove: () => void }) {
  const { t } = useTranslation()
  const base = `/api/catalog/cars/${car.id}`
  // A new picture keeps its address, so the version makes the browser load it again.
  const [version, setVersion] = useState(0)
  const changed = () => {
    setVersion((v) => v + 1)
    onChange()
  }
  return (
    <li className="catalog-card class-car">
      <div className="catalog-media car">
        {car.has_preview ? (
          <img src={`${base}/images/preview?v=${version}`} alt="" />
        ) : (
          <span className="catalog-missing">{t('catalog.noImage')}</span>
        )}
        {car.has_badge && <img className="catalog-badge" src={`${base}/images/badge?v=${version}`} alt="" />}
      </div>
      <div className="catalog-body">
        <div className="catalog-title">
          <h4 title={car.name}>{car.name}</h4>
          <CatalogEdit
            name={car.name}
            fields={carFields(car, t)}
            base={base}
            deleteTarget={{ kind: 'car', id: car.id, name: car.name }}
            images={[
              { kind: 'preview', set: car.has_preview },
              { kind: 'badge', set: car.has_badge },
            ]}
            items={[{ label: t('classes.removeCar'), onSelect: onRemove }]}
            onChange={changed}
          />
        </div>
        {(car.brand || car.year) && <p className="muted">{[car.brand, car.year].filter(Boolean).join(' · ')}</p>}
      </div>
    </li>
  )
}
