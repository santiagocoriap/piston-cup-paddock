import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { BallotOptionPicker } from './BallotOptionPicker'

afterEach(() => vi.restoreAllMocks())

const ballot = { id: 4, kind: 'track' } as Parameters<typeof BallotOptionPicker>[0]['ballot']
const candidates = [
  { id: 1, group: 'Barcelona', label: 'GP', image_url: null, status: 'added' },
  { id: 2, group: 'Bathurst', label: 'GP', image_url: null, status: 'ok' },
  { id: 3, group: 'Highlands', label: 'Long', image_url: null, status: 'track_excluded' },
]

describe('BallotOptionPicker', () => {
  it('ticks every option that can go in and saves the list', async () => {
    const calls = mockApi({
      'GET /api/ballots/4/candidates': () => json(200, candidates),
      'PUT /api/ballots/4/options': () => json(200, {}),
    })
    const done = vi.fn()
    renderPage(<BallotOptionPicker ballot={ballot} onDone={done} />, { path: '/', url: '/', me: ADMIN })
    expect(await screen.findByText('Excluida de esta votación')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Elegir las 2 disponibles'))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar (2 opciones)' }))
    expect(calls.find((c) => c.key === 'PUT /api/ballots/4/options')!.body).toEqual({ ids: [1, 2] })
    expect(done).toHaveBeenCalled()
  })

  it('removes an option when the admin unticks it', async () => {
    const calls = mockApi({
      'GET /api/ballots/4/candidates': () => json(200, candidates),
      'PUT /api/ballots/4/options': () => json(200, {}),
    })
    renderPage(<BallotOptionPicker ballot={ballot} onDone={() => undefined} />, { path: '/', url: '/', me: ADMIN })
    await userEvent.click(await screen.findByRole('checkbox', { name: /Barcelona/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar (0 opciones)' }))
    expect(calls.find((c) => c.key === 'PUT /api/ballots/4/options')!.body).toEqual({ ids: [] })
  })
})
