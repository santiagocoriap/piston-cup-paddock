import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icon'

// An item runs onSelect, or it is a link to a file to download (href). A danger item (a
// delete) is red, after a line, at the end of the menu.
export type MenuItem = { label: string; onSelect?: () => void; href?: string; danger?: boolean }

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
  // "below" and "above" are the bottom and the top of the button when the menu opened.
  const [place, setPlace] = useState<{ top: number; right: number; below: number; above: number } | null>(null)
  const list = useRef<HTMLUListElement>(null)
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
      if (!box || box.bottom !== place.below) close()
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
  useLayoutEffect(() => {
    const height = list.current?.offsetHeight ?? 0
    if (!place || place.top !== place.below + 4) return
    const fitsBelow = place.below + 4 + height <= window.innerHeight - 8
    const fitsAbove = place.above - 4 - height >= 8
    if (!fitsBelow && fitsAbove) setPlace({ ...place, top: place.above - 4 - height })
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
          setPlace({ top: box.bottom + 4, right: window.innerWidth - box.right, below: box.bottom, above: box.top })
        }}
      >
        {trigger ?? <Icon name="more" />}
      </button>
      {place && (
        <ul ref={list} className="row-menu-list" style={{ top: place.top, right: place.right }}>
          {[...items.filter((item) => !item.danger), ...items.filter((item) => item.danger)].map((item) => (
            <li key={item.label} className={item.danger ? 'danger' : undefined}>
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
