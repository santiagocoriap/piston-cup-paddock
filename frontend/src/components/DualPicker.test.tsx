import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import '../i18n'
import { DualPicker } from './DualPicker'

const items = [
  { id: 1, title: 'Acura' },
  { id: 2, title: 'Cadillac', subtitle: 'GM' },
  { id: 3, title: 'Ferrari', blocked: 'No entra' },
]

function Harness() {
  const [value, setValue] = useState<number[]>([1])
  return (
    <form aria-label="f">
      <DualPicker name="ids" items={items} value={value} onChange={setValue} />
    </form>
  )
}

const panel = (name: string) => screen.getByRole('region', { name })

describe('DualPicker', () => {
  it('moves a card with its button and by dragging, and keeps the ids in hidden inputs', async () => {
    const { container } = render(<Harness />)
    expect(within(panel('Elegidos')).getByText('Acura')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Agregar Cadillac' }))
    expect(within(panel('Elegidos')).getByText('Cadillac')).toBeInTheDocument()
    fireEvent.drop(panel('Disponibles'), { dataTransfer: { getData: () => '1' } })
    expect(within(panel('Disponibles')).getByText('Acura')).toBeInTheDocument()
    fireEvent.drop(panel('Elegidos'), { dataTransfer: { getData: () => '1' } })
    const ids = [...container.querySelectorAll('input[name="ids"]')].map((i) => (i as HTMLInputElement).value)
    expect(ids).toEqual(['2', '1'])
  })

  it('searches the available panel only and does not move a blocked card', async () => {
    render(<Harness />)
    expect(screen.getByRole('button', { name: 'Agregar Ferrari' })).toBeDisabled()
    expect(screen.getByText('No entra')).toBeInTheDocument()
    fireEvent.drop(panel('Elegidos'), { dataTransfer: { getData: () => '3' } })
    expect(within(panel('Elegidos')).queryByText('Ferrari')).not.toBeInTheDocument()
    await userEvent.type(screen.getByRole('searchbox'), 'gm')
    // Acura is chosen, so the search does not hide it.
    expect(within(panel('Elegidos')).getByText('Acura')).toBeInTheDocument()
    expect(within(panel('Disponibles')).getByText('Cadillac')).toBeInTheDocument()
    expect(within(panel('Disponibles')).queryByText('Ferrari')).not.toBeInTheDocument()
  })
})

describe('DualPicker filters', () => {
  it('filters by origin and by tag', async () => {
    const cars = [
      { id: 1, title: 'Acura', origin: { key: 'base', label: 'Juego base' }, tags: ['gt3'] },
      { id: 2, title: 'Cadillac', origin: { key: 'mod', label: 'Mod' }, tags: ['gt3', 'street'] },
      { id: 3, title: 'Ferrari', origin: { key: 'mod', label: 'Mod' } },
    ]
    render(<DualPicker items={cars} value={[]} onChange={() => undefined} />)
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Origen' }), 'mod')
    expect(screen.queryByText('Acura')).not.toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Etiqueta' }), 'street')
    expect(screen.getByText('Cadillac')).toBeInTheDocument()
    expect(screen.queryByText('Ferrari')).not.toBeInTheDocument()
  })
})

describe('DualPicker tracks', () => {
  const layouts = [
    { id: 1, group: 'Spa', title: 'GP' },
    { id: 2, group: 'Spa', title: 'Endurance' },
    { id: 3, group: 'Monza', title: 'GP' },
  ]
  function Tracks() {
    const [value, setValue] = useState<number[]>([])
    return <DualPicker items={layouts} value={value} onChange={setValue} />
  }

  it('shows the layouts of one track as one card, and a track with one layout as a plain card', async () => {
    render(<Tracks />)
    const available = within(panel('Disponibles'))
    expect(available.getAllByText('Spa')).toHaveLength(1)
    expect(available.getByText('Endurance')).toBeInTheDocument()
    expect(available.getByText('Monza')).toBeInTheDocument()
    await userEvent.click(available.getByRole('button', { name: 'Agregar Spa Endurance' }))
    const chosen = within(panel('Elegidos'))
    expect(chosen.getByText('Spa')).toBeInTheDocument()
    expect(chosen.getByText('Endurance')).toBeInTheDocument()
    expect(chosen.queryByText('GP')).not.toBeInTheDocument()
    await userEvent.click(within(panel('Disponibles')).getByRole('button', { name: 'Agregar Spa' }))
    expect(within(panel('Elegidos')).getByText('GP')).toBeInTheDocument()
  })
})
