import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { ServerPushPanel } from './ServerPushPanel'

afterEach(() => vi.restoreAllMocks())

const setup = (latest: unknown) => ({
  track: { key: 'ks_highlands', layout: 'layout_long' },
  entries: [
    { number: 7, name: 'Ana', team: 'Rojo', guid: '76561190000000001', model: 'trr_lmdh_acura_arx-06', ballast_kg: 15, restrictor_pct: 2 },
    { number: 8, name: 'Bob', team: '', guid: '', model: 'trr_lmdh_acura_arx-06', ballast_kg: 0, restrictor_pct: 0 },
  ],
  conditions: { sun_angle: 40, air_temp_c: 24, road_offset_c: 7, grip_pct: 89 },
  warnings: ['no_guid:Bob', 'weather_kept'],
  open_slots: 10,
  latest,
  has_collector: true,
})

describe('ServerPushPanel', () => {
  it('shows what goes to the server and sends it', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/server-setup': () => json(200, setup(null)),
      'POST /api/rounds/9/server-push': () =>
        json(200, setup({ id: 1, status: 'pending', error: '', requested_by: 'santi', requested_at: '2026-10-14T21:00:00Z', finished_at: null, collector: null })),
    })
    renderPage(<ServerPushPanel roundId={9} />, { path: '/', url: '/' })
    expect(await screen.findByText('Ana')).toBeInTheDocument()
    expect(screen.getByText('15 kg')).toBeInTheDocument()
    expect(screen.getByText('15:30')).toBeInTheDocument()
    expect(screen.getByText('31 °C')).toBeInTheDocument()
    expect(screen.getByText('Bob no tiene Steam ID: su lugar no queda reservado.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Enviar al servidor' }))
    expect(await screen.findByText(/Espera al colector/)).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/rounds/9/server-push')).toBe(true)
  })

  it('sends another number of open slots for one push', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/server-setup': () => json(200, setup(null)),
      'POST /api/rounds/9/server-push': () => json(200, setup(null)),
    })
    renderPage(<ServerPushPanel roundId={9} />, { path: '/', url: '/' })
    const input = await screen.findByLabelText(/Lugares libres/)
    expect(input).toHaveAttribute('placeholder', '10')
    await userEvent.type(input, '4')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar al servidor' }))
    await screen.findByText('Ana')
    expect(calls.find((c) => c.key === 'POST /api/rounds/9/server-push')?.body).toEqual({ open_slots: 4 })
  })
})
