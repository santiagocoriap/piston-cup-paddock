import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { api } from '../api/client'
import { DeleteButton } from './DeleteButton'

afterEach(() => vi.restoreAllMocks())

function page(onDone: () => void) {
  renderPage(
    <DeleteButton
      label="Eliminar"
      confirm="¿Seguro?"
      run={() => api.DELETE('/api/catalog/classes/{class_id}', { params: { path: { class_id: 5 } } })}
      onDone={onDone}
    />,
    { path: '/x', url: '/x' },
  )
}

describe('DeleteButton', () => {
  it('asks first and does nothing when the answer is no', async () => {
    const calls = mockApi({})
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const onDone = vi.fn()
    page(onDone)
    await userEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    expect(calls).toHaveLength(0)
    expect(onDone).not.toHaveBeenCalled()
  })

  it('deletes after the answer yes', async () => {
    const calls = mockApi({ 'DELETE /api/catalog/classes/5': () => json(204) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onDone = vi.fn()
    page(onDone)
    await userEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(calls.map((c) => c.key)).toEqual(['DELETE /api/catalog/classes/5'])
  })

  it('shows why a delete is refused', async () => {
    mockApi({ 'DELETE /api/catalog/classes/5': () => json(409, { detail: 'in_use' }) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onDone = vi.fn()
    page(onDone)
    await userEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Algo todavía usa este elemento')
    expect(onDone).not.toHaveBeenCalled()
  })
})
