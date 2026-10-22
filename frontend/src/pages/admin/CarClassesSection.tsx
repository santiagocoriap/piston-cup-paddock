import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { DangerMenu } from '../../components/DangerMenu'
import { Dialog } from '../../components/Dialog'
import { DualPicker, type PickItem } from '../../components/DualPicker'
import type { MenuItem } from '../../components/RowMenu'
import { CatalogEdit } from './CatalogEdit'
import { CarStats } from './CatalogFacts'
import { carFields } from './catalogFields'

type CarClass = components['schemas']['CarClassOut']
type Car = components['schemas']['CarOut']

/** Car classes and their cars. A class can hold subclasses, one level deep: each subclass card
 * shows inside its class. A change of the cars keeps the old rows in the history.
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
  const ids = new Set(classes.map((item) => item.id))
  // A subclass whose parent is not in the list shows as a main class.
  const mains = classes.filter((item) => item.parent_id === null || !ids.has(item.parent_id))
  return (
    <section aria-label={t('classes.title')} className="class-list">
      {mains.map((item) => (
        <ClassCard
          key={item.id}
          item={item}
          classes={classes}
          cars={cars}
          onSaved={onSaved}
          onCarsChanged={onCarsChanged}
        />
      ))}
    </section>
  )
}

type CardProps = {
  item: CarClass
  classes: CarClass[]
  cars: Car[]
  onSaved: () => void
  onCarsChanged: () => void
}

function ClassCard({ item, classes, cars, onSaved, onCarsChanged }: CardProps) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [changing, setChanging] = useState(false)
  const [adding, setAdding] = useState(false)
  const [picked, setPicked] = useState(item.car_ids)
  const [error, setError] = useState<string | null>(null)
  const subclasses = classes.filter((other) => other.parent_id === item.id)
  const isSub = item.parent_id !== null
  // Only a main class with no subclasses of its own can move under another main class.
  const parents = classes.filter((other) => other.parent_id === null && other.id !== item.id)
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

  const menu: MenuItem[] = [
    { label: t('classes.edit'), onSelect: () => setEditing(true) },
    ...(isSub ? [] : [{ label: t('classes.newSubclass'), onSelect: () => setAdding(true) }]),
    {
      label: t('classes.editCars'),
      onSelect: () => {
        setPicked(item.car_ids)
        setChanging(true)
      },
    },
  ]

  return (
    <div className={isSub ? 'card class-card subclass-card' : 'card class-card'}>
      <div className="class-head">
        <h3>
          {item.name}{' '}
          <span className="muted class-count">
            {[
              t('classes.carCount', { count: members.length }),
              ...(subclasses.length > 0 ? [t('classes.subclassCount', { count: subclasses.length })] : []),
            ].join(' · ')}
          </span>
        </h3>
        <DangerMenu target={{ kind: 'car_class', id: item.id, name: item.name }} onDeleted={onSaved} items={menu} />
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
        subclasses.length === 0 && <p className="muted">{t('classes.noCars')}</p>
      )}
      {changing && (
        <ActionForm
          title={t('classes.carsOf', { name: item.name })}
          submitLabel={t('common.save')}
          onDone={() => setChanging(false)}
          onSubmit={async (form) => {
            const problem = await saveCars(form.getAll('car_ids').map(Number), String(form.get('reason') ?? ''))
            if (!problem) setChanging(false)
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
      {subclasses.length > 0 && (
        <div className="subclass-list">
          {subclasses.map((sub) => (
            <ClassCard
              key={sub.id}
              item={sub}
              classes={classes}
              cars={cars}
              onSaved={onSaved}
              onCarsChanged={onCarsChanged}
            />
          ))}
        </div>
      )}
      <Dialog open={editing} title={t('classes.edit')} onClose={() => setEditing(false)}>
        {editing && (
          <ActionForm
            title={t('classes.edit')}
            submitLabel={t('common.save')}
            onDone={() => setEditing(false)}
            onSubmit={async (form) => {
              const parent = String(form.get('parent_id') ?? '')
              const { error } = await api.PATCH('/api/catalog/classes/{class_id}', {
                params: { path: { class_id: item.id } },
                body: {
                  name: String(form.get('name') ?? ''),
                  ...(subclasses.length === 0 ? { parent_id: parent ? Number(parent) : null } : {}),
                },
              })
              if (!error) {
                setEditing(false)
                onSaved()
              }
              return error
            }}
          >
            <label>
              {t('classes.name')}
              <input name="name" defaultValue={item.name} required maxLength={60} />
            </label>
            {subclasses.length === 0 && (
              <ParentSelect parents={parents} value={item.parent_id} />
            )}
          </ActionForm>
        )}
      </Dialog>
      <Dialog open={adding} title={t('classes.newSubclass')} onClose={() => setAdding(false)}>
        {adding && (
          <ActionForm
            title={t('classes.newSubclass')}
            submitLabel={t('common.create')}
            onDone={() => setAdding(false)}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/catalog/classes', {
                body: { name: String(form.get('name') ?? ''), parent_id: item.id },
              })
              if (!error) {
                setAdding(false)
                onSaved()
              }
              return error
            }}
          >
            <label>
              {t('classes.name')}
              <input name="name" required maxLength={60} />
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

/** The parent class of a class: none (a main class), or one of the main classes. */
export function ParentSelect({ parents, value }: { parents: CarClass[]; value: number | null }) {
  const { t } = useTranslation()
  return (
    <label>
      {t('classes.parent')}
      <select name="parent_id" defaultValue={value === null ? '' : String(value)}>
        <option value="">{t('classes.noParent')}</option>
        {parents.map((parent) => (
          <option key={parent.id} value={parent.id}>
            {parent.name}
          </option>
        ))}
      </select>
    </label>
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
