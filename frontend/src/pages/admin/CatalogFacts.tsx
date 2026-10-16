import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { components } from '../../api/schema'

type Layout = components['schemas']['LayoutOut']
type Car = components['schemas']['CarOut']

const format = (value: number, language: string) => new Intl.NumberFormat(language).format(value)

/** Up to 4 main numbers of a card, each with a short label. An empty value shows a dash. */
function Stats({ items }: { items: { label: string; value: string | null }[] }) {
  return (
    <dl className="catalog-stats">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function LayoutStats({ layout }: { layout: Layout }) {
  const { t, i18n } = useTranslation()
  return (
    <Stats
      items={[
        {
          label: t('facts.length'),
          value: layout.length_m ? `${format(layout.length_m / 1000, i18n.language)} km` : null,
        },
        { label: t('facts.width'), value: layout.width_m ? `${layout.width_m} m` : null },
        { label: t('facts.pitBoxes'), value: layout.pit_boxes ? String(layout.pit_boxes) : null },
        { label: t('facts.direction'), value: layout.direction ? t(`facts.directions.${layout.direction}`) : null },
      ]}
    />
  )
}

export function CarStats({ car }: { car: Car }) {
  const { t, i18n } = useTranslation()
  const unit = (value: number | null, text: string) => (value ? `${format(value, i18n.language)} ${text}` : null)
  return (
    <Stats
      items={[
        { label: t('facts.power'), value: unit(car.power_hp, 'hp') },
        { label: t('facts.torque'), value: unit(car.torque_nm, 'Nm') },
        { label: t('facts.weight'), value: unit(car.weight_kg, 'kg') },
        { label: t('facts.topSpeed'), value: unit(car.top_speed_kmh, 'km/h') },
      ]}
    />
  )
}

/** The other facts, folded under "Ficha técnica". A row without a value is not shown. */
function Sheet({ rows, description, tags }: { rows: [string, ReactNode][]; description: string; tags: string[] }) {
  const { t } = useTranslation()
  const shown = rows.filter(([, value]) => value !== null && value !== '' && value !== undefined)
  if (shown.length === 0 && !description && tags.length === 0) return null
  return (
    <details>
      <summary>{t('facts.sheet')}</summary>
      {description && <p className="catalog-description">{description}</p>}
      {shown.length > 0 && (
        <dl className="catalog-sheet">
          {shown.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {tags.length > 0 && (
        <p className="car-classes">
          {tags.map((tag) => (
            <span key={tag} className="badge chip">
              {tag}
            </span>
          ))}
        </p>
      )}
    </details>
  )
}

function WebLink({ url }: { url: string }) {
  if (!/^https?:\/\//i.test(url)) return null
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow">
      {url.replace(/^https?:\/\//i, '').replace(/\/$/, '')}
    </a>
  )
}

export function LayoutSheet({ layout }: { layout: Layout }) {
  const { t } = useTranslation()
  const place = [layout.city, layout.country].filter(Boolean).join(', ')
  const position =
    typeof layout.latitude === 'number' && typeof layout.longitude === 'number' ? (
      <a
        key="position"
        href={`https://www.openstreetmap.org/?mlat=${layout.latitude}&mlon=${layout.longitude}#map=14/${layout.latitude}/${layout.longitude}`}
        target="_blank"
        rel="noopener noreferrer"
      >
        {layout.latitude.toFixed(4)}, {layout.longitude.toFixed(4)}
      </a>
    ) : null
  return (
    <Sheet
      description={layout.description}
      tags={layout.tags ?? []}
      rows={[
        [t('facts.place'), place],
        [t('facts.position'), position],
        [t('facts.year'), layout.year],
        [t('facts.author'), layout.author],
        [t('facts.version'), layout.version],
        [t('facts.url'), layout.url ? <WebLink key="url" url={layout.url} /> : null],
      ]}
    />
  )
}

export function CarSheet({ car }: { car: Car }) {
  const { t } = useTranslation()
  return (
    <Sheet
      description={car.description}
      tags={car.tags ?? []}
      rows={[
        [t('facts.brand'), car.brand],
        [t('facts.country'), car.country],
        [t('facts.year'), car.year],
        [t('facts.gameClass'), car.game_class],
        [t('facts.acceleration'), car.acceleration],
        [t('facts.powerToWeight'), car.power_to_weight],
        [t('facts.author'), car.author],
        [t('facts.version'), car.version],
        [t('facts.url'), car.url ? <WebLink key="url" url={car.url} /> : null],
      ]}
    />
  )
}
