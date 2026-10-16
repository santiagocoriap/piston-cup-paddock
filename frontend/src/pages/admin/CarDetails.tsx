import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import type { components } from '../../api/schema'

type Car = components['schemas']['CarOut']
type Ini = Record<string, Record<string, Record<string, string | number>>>
type CarData = { ini?: Ini; lut?: Record<string, number[][]> }

/** Where the car comes from: the base game, a DLC (with its store page), or a mod. */
export function SourceBadge({ car }: { car: Car }) {
  const { t } = useTranslation()
  const label = t(`carDetail.source.${car.source}`)
  const store = car.source === 'dlc' && /^https?:\/\//i.test(car.source_url)
  return store ? (
    <a className={`badge source-${car.source}`} href={car.source_url} target="_blank" rel="noopener noreferrer nofollow">
      {label}
    </a>
  ) : (
    <span className={`badge source-${car.source}`}>{label}</span>
  )
}

/** The skins of the car, with their small pictures. */
function Skins({ car }: { car: Car }) {
  const { t } = useTranslation()
  return (
    <ul className="car-skins">
      {car.skins.map((skin) => (
        <li key={skin.id} title={skin.key}>
          {skin.has_preview ? <img src={`/api/catalog/skins/${skin.id}/preview`} alt="" loading="lazy" /> : <span className="car-skin-blank" />}
          <span>{skin.name || skin.key}</span>
          {(skin.number || skin.team) && <small className="muted">{[skin.number && `#${skin.number}`, skin.team].filter(Boolean).join(' · ')}</small>}
        </li>
      ))}
      {car.skins.length === 0 && <li className="muted">{t('carDetail.noSkins')}</li>}
    </ul>
  )
}

/** The tyre compounds of tyres.ini: name, size, and the ideal pressure. */
function Tyres({ car }: { car: Car }) {
  const { t } = useTranslation()
  const mm = (metres?: number | null) => (metres ? Math.round(metres * 1000) : '–')
  return (
    <table className="car-tyres">
      <thead>
        <tr>
          <th>{t('carDetail.compound')}</th>
          <th>{t('carDetail.front')}</th>
          <th>{t('carDetail.rear')}</th>
          <th>{t('carDetail.pressure')}</th>
        </tr>
      </thead>
      <tbody>
        {car.tyres.map((tyre) => (
          <tr key={tyre.index}>
            <th scope="row">
              {tyre.name || `#${tyre.index}`}
              {tyre.short_name && <span className="badge chip">{tyre.short_name}</span>}
            </th>
            <td>
              {mm(tyre.front.width)} mm / R{mm(tyre.front.radius)}
            </td>
            <td>
              {mm(tyre.rear.width)} mm / R{mm(tyre.rear.radius)}
            </td>
            <td>{tyre.front.pressure_ideal ?? '–'} psi</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Every number of the data folder, loaded when the admin opens it (it is large). */
function FullData({ car }: { car: Car }) {
  const { t } = useTranslation()
  const [data, setData] = useState<CarData | null>(null)
  const [failed, setFailed] = useState(false)
  async function load() {
    if (data) return
    const { data: loaded, error } = await api.GET('/api/catalog/cars/{car_id}/data', { params: { path: { car_id: car.id } } })
    if (error || !loaded) return setFailed(true)
    setData(loaded as CarData)
  }
  return (
    <details onToggle={(event) => event.currentTarget.open && void load()}>
      <summary>{t('carDetail.allData')}</summary>
      {failed && <p role="alert">{t('carDetail.loadFailed')}</p>}
      {Object.entries(data?.ini ?? {}).map(([file, sections]) => (
        <details key={file} className="car-data-file">
          <summary>{file}.ini</summary>
          {Object.entries(sections).map(([section, values]) => (
            <dl key={section} className="catalog-sheet">
              <h4>{section}</h4>
              {Object.entries(values).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          ))}
        </details>
      ))}
      {data?.lut && (
        <details className="car-data-file">
          <summary>{t('carDetail.curves', { count: Object.keys(data.lut).length })}</summary>
          <ul>
            {Object.entries(data.lut).map(([name, points]) => (
              <li key={name}>
                {name}: {t('carDetail.points', { count: points.length })}
              </li>
            ))}
          </ul>
        </details>
      )}
    </details>
  )
}

/** The skins, the tyres, and the data folder of a car, each folded. */
export function CarDetails({ car }: { car: Car }) {
  const { t } = useTranslation()
  return (
    <>
      <details>
        <summary>{t('carDetail.skins', { count: car.skins.length })}</summary>
        <Skins car={car} />
      </details>
      {car.tyres.length > 0 && (
        <details>
          <summary>{t('carDetail.tyres', { count: car.tyres.length })}</summary>
          <Tyres car={car} />
        </details>
      )}
      {car.has_data && <FullData car={car} />}
      {car.data_error && <p className="muted">{t('carDetail.dataError')}</p>}
    </>
  )
}
