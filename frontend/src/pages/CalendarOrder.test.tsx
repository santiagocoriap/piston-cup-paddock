import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { CalendarOrder } from './CalendarOrder'

afterEach(() => vi.restoreAllMocks())

const round = (id: number, number: number, track: string) => ({
  id, number, track_layout_id: id, track_name: track, layout_name: 'GP', scheduled_at: null, origin: 'voted',
  cancelled: false, cancel_reason: '', track_changes: [], announced_conditions: {},
})

describe('CalendarOrder', () => {
  it('moves a round and saves the order and a new date', async () => {
    const calls = mockApi({
      'PUT /api/seasons/5/round-order': () => json(200, []),
      'PATCH /api/rounds/2/calendar': () => json(200, round(2, 1, 'Bathurst')),
    })
    const saved = vi.fn()
    renderPage(
      <CalendarOrder seasonId={5} rounds={[round(1, 1, 'Barcelona'), round(2, 2, 'Bathurst')]} onSaved={saved} />,
      { path: '/', url: '/', me: ADMIN },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Subir Bathurst' }))
    await userEvent.type(screen.getByLabelText('Día y hora de Bathurst'), '2026-11-01T21:30')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Calendario guardado.')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'PUT /api/seasons/5/round-order')!.body).toEqual({ round_ids: [2, 1] })
    const patch = calls.find((c) => c.key === 'PATCH /api/rounds/2/calendar')!.body as { scheduled_at: string }
    expect(patch.scheduled_at).toMatch(/^2026-11-01T21:30:00/)
    expect(saved).toHaveBeenCalled()
  })
})
