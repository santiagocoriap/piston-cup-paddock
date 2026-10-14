import type { components } from '../../api/schema'
import type { EditField } from './CatalogEdit'

type Layout = components['schemas']['LayoutOut']
type Car = components['schemas']['CarOut']

/** The fields of the edit dialog of a layout. */
export function layoutFields(layout: Layout, t: (key: string) => string): EditField[] {
  return [
    { name: 'name', label: t('catalogEdit.name'), kind: 'text', value: layout.name, required: true, max: 200 },
    { name: 'length_m', label: t('facts.lengthM'), kind: 'number', value: layout.length_m, min: 100, max: 100000 },
    { name: 'width_m', label: t('facts.widthM'), kind: 'number', value: layout.width_m, min: 1, max: 100 },
    { name: 'pit_boxes', label: t('facts.pitBoxes'), kind: 'number', value: layout.pit_boxes, min: 1, max: 200 },
    {
      name: 'direction',
      label: t('facts.direction'),
      kind: 'select',
      value: layout.direction,
      options: [
        ['', '—'],
        ['clockwise', t('facts.directions.clockwise')],
        ['anticlockwise', t('facts.directions.anticlockwise')],
      ],
    },
    { name: 'country', label: t('facts.country'), kind: 'text', value: layout.country, max: 100 },
    { name: 'city', label: t('facts.city'), kind: 'text', value: layout.city, max: 100 },
    { name: 'latitude', label: t('facts.latitude'), kind: 'number', value: layout.latitude, min: -90, max: 90, step: 'any' },
    { name: 'longitude', label: t('facts.longitude'), kind: 'number', value: layout.longitude, min: -180, max: 180, step: 'any' },
    { name: 'year', label: t('facts.year'), kind: 'number', value: layout.year, min: 1880, max: 2100 },
    { name: 'author', label: t('facts.author'), kind: 'text', value: layout.author, max: 200 },
    { name: 'version', label: t('facts.version'), kind: 'text', value: layout.version, max: 50 },
    { name: 'url', label: t('facts.url'), kind: 'url', value: layout.url, max: 300 },
    { name: 'tags', label: t('facts.tags'), kind: 'tags', value: layout.tags ?? [] },
    { name: 'description', label: t('facts.description'), kind: 'textarea', value: layout.description, max: 5000 },
  ]
}

/** The fields of the edit dialog of a car. */
export function carFields(car: Car, t: (key: string) => string): EditField[] {
  return [
    { name: 'name', label: t('catalogEdit.name'), kind: 'text', value: car.name, required: true, max: 200 },
    { name: 'brand', label: t('facts.brand'), kind: 'text', value: car.brand, max: 100 },
    { name: 'power_hp', label: t('facts.powerHp'), kind: 'number', value: car.power_hp, min: 1, max: 5000 },
    { name: 'torque_nm', label: t('facts.torqueNm'), kind: 'number', value: car.torque_nm, min: 1, max: 10000 },
    { name: 'weight_kg', label: t('facts.weightKg'), kind: 'number', value: car.weight_kg, min: 1, max: 20000 },
    { name: 'top_speed_kmh', label: t('facts.topSpeedKmh'), kind: 'number', value: car.top_speed_kmh, min: 1, max: 1500 },
    { name: 'acceleration', label: t('facts.acceleration'), kind: 'text', value: car.acceleration, max: 60 },
    { name: 'power_to_weight', label: t('facts.powerToWeight'), kind: 'text', value: car.power_to_weight, max: 60 },
    { name: 'game_class', label: t('facts.gameClass'), kind: 'text', value: car.game_class, max: 60 },
    { name: 'country', label: t('facts.country'), kind: 'text', value: car.country, max: 100 },
    { name: 'year', label: t('facts.year'), kind: 'number', value: car.year, min: 1880, max: 2100 },
    { name: 'author', label: t('facts.author'), kind: 'text', value: car.author, max: 200 },
    { name: 'version', label: t('facts.version'), kind: 'text', value: car.version, max: 50 },
    { name: 'url', label: t('facts.url'), kind: 'url', value: car.url, max: 300 },
    { name: 'tags', label: t('facts.tags'), kind: 'tags', value: car.tags ?? [] },
    { name: 'description', label: t('facts.description'), kind: 'textarea', value: car.description, max: 5000 },
  ]
}
