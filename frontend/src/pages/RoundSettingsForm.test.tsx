import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { RoundSettingsForm } from './RoundSettingsForm'

afterEach(() => vi.restoreAllMocks())

const round = {
  id: 4, number: 2, track_layout_id: 4, track_name: 'Spa', layout_name: 'GP', scheduled_at: null, origin: 'voted',
  cancelled: false, cancel_reason: '', track_changes: [],
  announced_conditions: { weather: 'sol_01_clear', air_temp_c: 22, time_of_day: '', track_temp_c: null, grip: '', notes: '' },
}

describe('RoundSettingsForm', () => {
  it('shows the current conditions and saves the changes', async () => {
    const calls = mockApi({ 'PATCH /api/rounds/4/calendar': () => json(200, round) })
    const changed = vi.fn()
    renderPage(<RoundSettingsForm round={round} onChange={changed} onDone={() => undefined} />, {
      path: '/',
      url: '/',
      me: ADMIN,
    })
    expect(screen.getByLabelText('Clima')).toHaveValue('sol_01_clear')
    const grip = screen.getByLabelText('Grip')
    await userEvent.type(grip, 'Optimum (100%)')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() => expect(changed).toHaveBeenCalled())
    const body = calls.find((c) => c.key === 'PATCH /api/rounds/4/calendar')!.body as {
      announced_conditions: Record<string, unknown>
    }
    expect(body.announced_conditions).toMatchObject({ weather: 'sol_01_clear', air_temp_c: 22, grip: 'Optimum (100%)' })
  })
})
