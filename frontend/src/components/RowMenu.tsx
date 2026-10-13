import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icon'

// An item runs onSelect, or it is a link to a file to download (href).
export type MenuItem = { label: string; onSelect?: () => void; href?: string }

/** A "more" button that opens a short list of row actions. The list is fixed to the screen,
 * so a table that scrolls cannot clip it. */
export function RowMenu({
  label,
  items,
  trigger,
}: {
  label: string
  items: MenuItem[]
  // Content for a labelled button. Without it, the button is the "more" icon.
  trigger?: ReactNode
}) {
  const [place, setPlace] = useState<{ top: number; right: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const open = place !== null
  useEffect(() => {
    if (!place) return
    const close = () => setPlace(null)
    // A scroll event can come late, after the click that opened the menu.
    // Close the menu only when the button really moved.
    const moved = () => {
      const box = button.current?.getBoundingClientRect()
      if (!box || box.bottom + 4 !== place.top) close()
    }
    const outside = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) close()
    }
    const escape = (event: globalThis.KeyboardEvent) => event.key === 'Escape' && close()
    document.addEventListener('mousedown', outside)
    document.addEventListener('keydown', escape)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', moved, true)
    return () => {
      document.removeEventListener('mousedown', outside)
      document.removeEventListener('keydown', escape)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', moved, true)
    }
  }, [place])
  return (
    <div className="row-menu" ref={ref}>
      <button
        ref={button}
        type="button"
        className={trigger ? 'secondary small menu-trigger' : 'icon-button'}
        aria-label={label}
        aria-expanded={open}
        onClick={(event) => {
          if (open) return setPlace(null)
          const box = event.currentTarget.getBoundingClientRect()
          setPlace({ top: box.bottom + 4, right: window.innerWidth - box.right })
        }}
      >
        {trigger ?? <Icon name="more" />}
      </button>
      {place && (
        <ul className="row-menu-list" style={{ top: place.top, right: place.right }}>
          {items.map((item) => (
            <li key={item.label}>
              {item.href ? (
                <a className="row-menu-link" href={item.href} download onClick={() => setPlace(null)}>
                  {item.label}
                </a>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setPlace(null)
                    item.onSelect?.()
                  }}
                >
                  {item.label}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
