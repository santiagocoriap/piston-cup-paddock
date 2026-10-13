import { useId, useState, type KeyboardEvent } from 'react'
import { Icon } from './Icon'

export type ComboboxOption = { value: string; label: string; hint?: string; disabled?: boolean }

type Props = {
  label: string
  options: ComboboxOption[]
  value: string
  onChange: (value: string) => void
  emptyText: string
}

/** A select with a search field. Type to filter, use the arrow keys, and press Enter to pick. */
export function Combobox({ label, options, value, onChange, emptyText }: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputId = useId()
  const listId = useId()
  const selected = options.find((option) => option.value === value)
  const needle = query.trim().toLowerCase()
  const shown = options.filter((option) => option.label.toLowerCase().includes(needle))

  function show() {
    setOpen(true)
    setQuery('')
    setActive(Math.max(0, options.findIndex((option) => option.value === value)))
  }

  function pick(option: ComboboxOption | undefined) {
    if (!option || option.disabled) return
    onChange(option.value)
    setOpen(false)
    setQuery('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) return show()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((old) => (shown.length === 0 ? 0 : (old + step + shown.length) % shown.length))
    } else if (event.key === 'Enter' && open) {
      event.preventDefault()
      pick(shown[active])
    } else if (event.key === 'Escape' && open) {
      // Close the list only. A second Escape closes the dialog around it.
      event.preventDefault()
      event.stopPropagation()
      setOpen(false)
      setQuery('')
    }
  }

  return (
    <div className="combobox">
      <label htmlFor={inputId}>{label}</label>
      <div className="combobox-field">
        <input
          id={inputId}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && shown[active] ? `${listId}-${active}` : undefined}
          autoComplete="off"
          value={open ? query : (selected?.label ?? '')}
          placeholder={selected?.label}
          onFocus={show}
          onClick={() => !open && show()}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            setQuery(event.target.value)
            setActive(0)
            setOpen(true)
          }}
          onKeyDown={onKeyDown}
        />
        <span className="combobox-chevron" aria-hidden="true">
          <Icon name="chevron" small />
        </span>
      </div>
      {open && (
        <ul id={listId} role="listbox" aria-label={label} className="combobox-list">
          {shown.map((option, index) => (
            <li
              key={option.value}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={option.value === value}
              aria-disabled={option.disabled || undefined}
              className={index === active ? 'active' : undefined}
              // Keep the focus in the input, so the list does not close before the click.
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActive(index)}
              onClick={() => pick(option)}
            >
              <span>{option.label}</span>
              {option.hint && <span className="combobox-hint">{option.hint}</span>}
              {option.value === value && <Icon name="check" small />}
            </li>
          ))}
          {shown.length === 0 && <li className="combobox-empty">{emptyText}</li>}
        </ul>
      )}
    </div>
  )
}
