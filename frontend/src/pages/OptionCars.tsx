import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Loading } from '../components/Layout'
import { useLoad } from '../lib/useLoad'

type Group = components['schemas']['CarGroupOut']

/** A button on a car class option that opens every car of the class, in groups by subclass.
 * The dialog goes to the end of the page, so a click in it does not choose the option. */
export function OptionCars({ ballotId, optionId, label, count }: { ballotId: number; optionId: number; label: string; count: number }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        className="secondary small option-cars-button"
        onClick={(event) => {
          // The button is inside the label of the option: it must not choose the option.
          event.preventDefault()
          event.stopPropagation()
          setOpen(true)
        }}
      >
        <Icon name="layers" small />
        {t('voting.seeCars', { count })}
      </button>
      {createPortal(
        <Dialog open={open} title={t('voting.carsOf', { name: label })} onClose={() => setOpen(false)}>
          {open && <CarList ballotId={ballotId} optionId={optionId} label={label} />}
        </Dialog>,
        document.body,
      )}
    </>
  )
}

function CarList({ ballotId, optionId, label }: { ballotId: number; optionId: number; label: string }) {
  const { t } = useTranslation()
  const groups = useLoad(
    () =>
      api.GET('/api/ballots/{ballot_id}/options/{option_id}/cars', {
        params: { path: { ballot_id: ballotId, option_id: optionId } },
      }),
    [ballotId, optionId],
  )
  return (
    <div className="modal-body option-cars">
      <h3>{t('voting.carsOf', { name: label })}</h3>
      {!groups.data ? (
        <Loading failed={groups.failed} />
      ) : groups.data.length === 0 ? (
        <p className="muted">{t('classes.noCars')}</p>
      ) : (
        groups.data.map((group: Group) => (
          <section key={group.subclass ?? ''} className="option-cars-group">
            {group.subclass && (
              <h4>
                {group.subclass} <span className="muted">{t('voting.carCount', { count: group.cars.length })}</span>
              </h4>
            )}
            <ul className="option-cars-grid">
              {group.cars.map((car) => (
                <li key={car.id}>
                  <span className="option-car-media">
                    {car.image_url ? <img src={car.image_url} alt="" loading="lazy" /> : <Icon name="flag" />}
                  </span>
                  <b>{car.name}</b>
                  {(car.brand || car.year) && (
                    <span className="muted">{[car.brand, car.year].filter(Boolean).join(' · ')}</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}
