import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { TelemetryCard } from './TelemetryCard'

afterEach(() => vi.restoreAllMocks())

const status = {
  has_driver: true, laps: 3, last_lap_at: '2026-10-14T23:55:00Z',
  sharing: { teammates: 'laps', drivers: 'none', admins: 'laps' },
}

describe('TelemetryCard', () => {
  it('shows the laps and saves who sees the telemetry', async () => {
    const calls = mockApi({
      'GET /api/me/telemetry': () => json(200, status),
      'PUT /api/me/telemetry/sharing': () => json(200, { teammates: 'full', drivers: 'laps', admins: 'laps' }),
    })
    renderPage(<TelemetryCard />, { path: '/account', url: '/account', me: DRIVER })
    expect(await screen.findByText('3 vueltas grabadas')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /clave/i })).toBeNull()

    // The driver can also give the full level to other drivers.
    const drivers = screen.getByLabelText('Otros pilotos')
    expect(drivers.querySelector('option[value="full"]')).not.toBeNull()
    await userEvent.selectOptions(screen.getByLabelText('Compañeros de equipo'), 'full')
    await userEvent.selectOptions(drivers, 'laps')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Guardado.')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'PUT /api/me/telemetry/sharing')!.body).toEqual({
      teammates: 'full', drivers: 'laps', admins: 'laps',
    })
  })
})
