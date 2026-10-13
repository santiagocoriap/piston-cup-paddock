import { useEffect, useRef, useState } from 'react'
import { Icon } from './Icon'

export type MenuItem = { label: string; onSelect: () => void }

/** A "more" button that opens a short list of row actions. The list is fixed to the screen,
 * so a table that scrolls cannot clip it. */
export function RowMenu({ label, items }: { label: string; items: MenuItem[] }) {
  const [place, setPlace] = useState<{ top: number; right: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const open = place !== null
  useEffect(() => {
    if (!open) return
    const close = () => setPlace(null)
    const outside = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) close()
    }
    const escape = (event: globalThis.KeyboardEvent) => event.key === 'Escape' && close()
    document.addEventListener('mousedown', outside)
    document.addEventListener('keydown', escape)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('mousedown', outside)
      document.removeEventListener('keydown', escape)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [open])
  return (
    <div className="row-menu" ref={ref}>
      <button
        type="button"
        className="icon-button"
        aria-label={label}
        aria-expanded={open}
        onClick={(event) => {
          if (open) return setPlace(null)
          const box = event.currentTarget.getBoundingClientRect()
          setPlace({ top: box.bottom + 4, right: window.innerWidth - box.right })
        }}
      >
        <Icon name="more" />
      </button>
      {place && (
        <ul className="row-menu-list" style={{ top: place.top, right: place.right }}>
          {items.map((item) => (
            <li key={item.label}>
              <button
                type="button"
                onClick={() => {
                  setPlace(null)
                  item.onSelect()
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
