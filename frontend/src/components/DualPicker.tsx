import { useMemo, useState, type DragEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export type PickItem = {
  id: number
  title: string
  subtitle?: string
  /** A track: the layouts of one track share a group (the track name), and show as one card
   * with a row for each layout. The title of a grouped item is its layout. */
  group?: string
  image?: string | null
  /** The shape of the picture: a car is wide and fills the box, a track is drawn inside it. */
  kind?: 'car' | 'track'
  /** Where it comes from (for a car: base game, DLC, mod). Adds an origin filter. */
  origin?: { key: string; label: string }
  /** Adds a tag filter. */
  tags?: string[]
  /** Quick facts under the name, for example the car stats. */
  details?: ReactNode
  /** Why the item cannot be picked. It stays in "available", greyed out, and cannot move. */
  blocked?: string
}

type Side = 'available' | 'chosen'
/** One card: a single item, or a track with some of its layouts. */
type Entry = { key: string; group?: string; items: PickItem[] }

/** Two panels, "Disponibles" and "Elegidos". Drag a card from one to the other, or use its
 * button. The search and the filters narrow "available"; "chosen" always lists every pick. A
 * track with several layouts is one card, and each layout moves alone (the card moves all).
 * With `name`, the chosen ids go in hidden inputs, so the picker works inside a form like a
 * group of checkboxes. */
export function DualPicker({
  items,
  value,
  onChange,
  name,
  searchLabel,
}: {
  items: PickItem[]
  value: number[]
  onChange: (ids: number[]) => void
  name?: string
  searchLabel?: string
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [origin, setOrigin] = useState('')
  const [tag, setTag] = useState('')
  const [from, setFrom] = useState<Side | null>(null)
  const [over, setOver] = useState<Side | null>(null)
  const [dragging, setDragging] = useState<number[]>([])

  const chosenSet = useMemo(() => new Set(value), [value])
  const words = query.trim().toLowerCase()
  const origins = [...new Map(items.flatMap((i) => (i.origin ? [[i.origin.key, i.origin.label] as const] : []))).entries()]
  const tagCounts = new Map<string, number>()
  for (const item of items) for (const name of new Set(item.tags ?? [])) tagCounts.set(name, (tagCounts.get(name) ?? 0) + 1)
  const tagList = [...tagCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  const layoutsOf = new Map<string, number>()
  for (const item of items) if (item.group) layoutsOf.set(item.group, (layoutsOf.get(item.group) ?? 0) + 1)
  const shown = items.filter(
    (item) =>
      (!words || `${item.group ?? ''} ${item.title} ${item.subtitle ?? ''}`.toLowerCase().includes(words)) &&
      (!origin || item.origin?.key === origin) &&
      (!tag || item.tags?.includes(tag)),
  )
  // The search and the filters narrow what is available. What is chosen always shows.
  const available = shown.filter((item) => !chosenSet.has(item.id))
  const chosen = items.filter((item) => chosenSet.has(item.id))
  const movable = available.filter((item) => !item.blocked)

  const add = (ids: number[]) => onChange([...value, ...ids.filter((id) => !chosenSet.has(id))])
  const remove = (ids: number[]) => onChange(value.filter((id) => !ids.includes(id)))

  /** Cards in order of first appearance. A track with one layout in all is a plain card. */
  function entriesOf(list: PickItem[]): Entry[] {
    const entries: Entry[] = []
    const groups = new Map<string, Entry>()
    for (const item of list) {
      if (!item.group || layoutsOf.get(item.group) === 1) {
        entries.push({ key: `i${item.id}`, items: [item] })
      } else if (groups.has(item.group)) {
        groups.get(item.group)!.items.push(item)
      } else {
        const entry = { key: `g${item.group}`, group: item.group, items: [item] }
        groups.set(item.group, entry)
        entries.push(entry)
      }
    }
    return entries
  }

  function drop(event: DragEvent, side: Side) {
    event.preventDefault()
    const ids = event.dataTransfer
      .getData('text/plain')
      .split(',')
      .map(Number)
      .filter((id) => items.some((item) => item.id === id && !item.blocked))
    setOver(null)
    setFrom(null)
    setDragging([])
    if (side === 'chosen') add(ids)
    else remove(ids)
  }

  function dragProps(side: Side, ids: number[]) {
    return {
      draggable: ids.length > 0,
      onDragStart: (event: DragEvent) => {
        event.stopPropagation()
        setFrom(side)
        setDragging(ids)
        event.dataTransfer.effectAllowed = 'move'
        // Firefox needs data to start a drag.
        event.dataTransfer.setData('text/plain', ids.join(','))
      },
      onDragEnd: () => {
        setFrom(null)
        setOver(null)
        setDragging([])
      },
    }
  }

  function moveButton(side: Side, ids: number[], label: string, blocked = false) {
    return (
      <button
        type="button"
        className="secondary small pick-move"
        disabled={blocked || ids.length === 0}
        aria-label={t(side === 'available' ? 'picker.add' : 'picker.remove', { name: label })}
        onClick={() => (side === 'available' ? add(ids) : remove(ids))}
      >
        {side === 'available' ? '+' : '×'}
      </button>
    )
  }

  function card(side: Side, entry: Entry) {
    const first = entry.items[0]
    const movableIds = entry.items.filter((i) => !i.blocked).map((i) => i.id)
    const image = entry.items.find((i) => i.image)?.image
    const plainTitle = first.group ?? first.title
    const plainSubtitle = first.group && first.title !== first.group ? first.title : first.subtitle
    const classes = [
      'pick-card',
      entry.group ? 'pick-group' : '',
      !entry.group && first.blocked ? 'blocked' : '',
      from === side && entry.items.some((i) => dragging.includes(i.id)) ? 'dragging' : '',
    ]
    return (
      <li key={entry.key} className={classes.filter(Boolean).join(' ')} {...dragProps(side, movableIds)}>
        <div className={`catalog-media ${first.kind ?? 'car'}`}>
          {image && <img src={image} alt="" loading="lazy" draggable={false} />}
        </div>
        <div className="pick-body">
          <div className="pick-title">
            <b title={entry.group ?? plainTitle}>{entry.group ?? plainTitle}</b>
            {moveButton(side, movableIds, entry.group ?? plainTitle, !entry.group && !!first.blocked)}
          </div>
          {!entry.group && plainSubtitle && <span className="muted">{plainSubtitle}</span>}
          {!entry.group && first.blocked && <span className="pick-why">{first.blocked}</span>}
          {!entry.group && first.details}
        </div>
        {entry.group && (
          <ul className="pick-layouts">
            {entry.items.map((item) => (
              <li
                key={item.id}
                className={item.blocked ? 'blocked' : undefined}
                {...dragProps(side, item.blocked ? [] : [item.id])}
              >
                <span className="pick-layout-name">
                  <span>{item.title}</span>
                  {item.blocked && <span className="pick-why">{item.blocked}</span>}
                </span>
                {moveButton(side, [item.id], `${entry.group} ${item.title}`, !!item.blocked)}
              </li>
            ))}
          </ul>
        )}
      </li>
    )
  }

  function panel(side: Side, list: PickItem[]) {
    const entries = entriesOf(list)
    return (
      <section
        className={['pick-panel', over === side && from !== side ? 'drop-here' : ''].filter(Boolean).join(' ')}
        aria-label={t(`picker.${side}`)}
        onDragOver={(event) => {
          event.preventDefault()
          setOver(side)
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(null)
        }}
        onDrop={(event) => drop(event, side)}
      >
        <header>
          <h4>
            {t(`picker.${side}`)} <span className="muted">({list.length})</span>
          </h4>
          {side === 'available' ? (
            <button type="button" className="secondary small" disabled={movable.length === 0} onClick={() => add(movable.map((i) => i.id))}>
              {t('picker.addAll', { count: movable.length })}
            </button>
          ) : (
            <button type="button" className="secondary small" disabled={chosen.length === 0} onClick={() => remove(chosen.map((i) => i.id))}>
              {t('picker.removeAll')}
            </button>
          )}
        </header>
        <ul className="pick-grid">
          {entries.map((entry) => card(side, entry))}
          {list.length === 0 && <li className="muted pick-empty">{t(side === 'available' ? 'picker.noneAvailable' : 'picker.noneChosen')}</li>}
        </ul>
      </section>
    )
  }

  return (
    <div className="dual-picker">
      <div className="pick-filters">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={searchLabel ?? t('picker.search')}
          aria-label={searchLabel ?? t('picker.search')}
        />
        {origins.length > 0 && (
          <select value={origin} onChange={(event) => setOrigin(event.target.value)} aria-label={t('picker.origin')}>
            <option value="">{t('picker.allOrigins')}</option>
            {origins.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        )}
        {tagList.length > 0 && (
          <select value={tag} onChange={(event) => setTag(event.target.value)} aria-label={t('picker.tag')}>
            <option value="">{t('picker.allTags')}</option>
            {tagList.map(([name, count]) => (
              <option key={name} value={name}>
                {name} ({count})
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="pick-panels">
        {panel('available', available)}
        {panel('chosen', chosen)}
      </div>
      {name && value.map((id) => <input key={id} type="hidden" name={name} value={id} />)}
    </div>
  )
}
