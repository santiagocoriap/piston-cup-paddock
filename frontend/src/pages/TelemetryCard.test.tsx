import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { TelemetryCard } from './TelemetryCard'
import { TelemetrySection } from './TelemetrySection'

afterEach(() => vi.restoreAllMocks())

const status = {
  has_driver: true, has_key: false, last_seen_at: null, laps: 0, last_lap_at: null,
  sharing: { teammates: 'laps', drivers: 'none', admins: 'laps' },
}

describe('TelemetryCard', () => {
  it('makes a key and saves who sees the telemetry', async () => {
    const calls = mockApi({
      'GET /api/me/telemetry': () => json(200, status),
      'POST /api/me/telemetry/key': () => json(200, { key: 'pdc_secret' }),
      'PUT /api/me/telemetry/sharing': () => json(200, { teammates: 'full', drivers: 'laps', admins: 'laps' }),
    })
    renderPage(<TelemetryCard />, { path: '/account', url: '/account', me: DRIVER })
    await userEvent.click(await screen.findByRole('button', { name: 'Crear clave' }))
    expect(await screen.findByDisplayValue('pdc_secret')).toBeInTheDocument()

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

describe('TelemetrySection', () => {
  it('shows a lap without inputs for lap access', async () => {
    const lap = { id: 4, driver_name: 'Ana', session_type: 'race', lap_number: 3, lap_time_ms: 189296, valid: true, access: 'laps' }
    mockApi({
      'GET /api/rounds/9/telemetry': () => json(200, [lap]),
      'GET /api/telemetry-laps/4': () =>
        json(200, { ...lap, sample_hz: 20, car: 'acura', channels: { t_ms: [0, 50], pos: [0, 0.5], speed_kmh: [200, 250] } }),
    })
    renderPage(<TelemetrySection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    await userEvent.click(await screen.findByRole('button', { name: /Ana · vuelta 3/ }))
    expect(await screen.findByRole('img', { name: 'Velocidad de Ana' })).toBeInTheDocument()
    expect(screen.getByText(/sin pedales: el piloto no los comparte/)).toBeInTheDocument()
  })
})
