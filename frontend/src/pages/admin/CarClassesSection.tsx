import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { DangerMenu } from '../../components/DangerMenu'

type CarClass = components['schemas']['CarClassOut']
type Car = components['schemas']['CarOut']

/** Car classes and their cars. A change keeps the old rows in the history. */
export function CarClassesSection({ cars, classes, onSaved }: { cars: Car[]; classes: CarClass[]; onSaved: () => void }) {
  const { t } = useTranslation()
  return (
    <section aria-label={t('classes.title')} className="class-list">
      {classes.map((item) => (
        <ClassCard key={item.id} item={item} cars={cars} onSaved={onSaved} />
      ))}
    </section>
  )
}

function ClassCard({ item, cars, onSaved }: { item: CarClass; cars: Car[]; onSaved: () => void }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const names = cars.filter((c) => item.car_ids.includes(c.id)).map((c) => c.name)
  return (
    <div className="card class-card">
      <div className="class-head">
        <h3>{item.name}</h3>
        <DangerMenu target={{ kind: 'car_class', id: item.id, name: item.name }} onDeleted={onSaved} />
      </div>
      <p>{names.length > 0 ? names.join(', ') : t('classes.noCars')}</p>
      <button type="button" className="secondary small" onClick={() => setEditing((e) => !e)}>
        {t('classes.editCars')}
      </button>
      {editing && (
        <ActionForm
          title={t('classes.carsOf', { name: item.name })}
          submitLabel={t('common.save')}
          onSubmit={async (form) => {
            const { error } = await api.PUT('/api/catalog/classes/{class_id}/cars', {
              params: { path: { class_id: item.id } },
              body: { car_ids: form.getAll('car_ids').map(Number), reason: String(form.get('reason') ?? '') },
            })
            if (!error) {
              setEditing(false)
              onSaved()
            }
            return error
          }}
        >
          <fieldset>
            <legend>{t('classes.cars')}</legend>
            {cars.map((car) => (
              <label key={car.id} className="check">
                <input type="checkbox" name="car_ids" value={car.id} defaultChecked={item.car_ids.includes(car.id)} />
                {car.name}
              </label>
            ))}
          </fieldset>
          <label>
            {t('classes.reason')}
            <input name="reason" maxLength={300} />
          </label>
        </ActionForm>
      )}
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
