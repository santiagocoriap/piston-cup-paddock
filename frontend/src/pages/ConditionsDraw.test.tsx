import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { ConditionsPoolForm, DrawHistory } from './ConditionsDraw'

afterEach(() => vi.restoreAllMocks())

const EMPTY = { weather: [], time_of_day: [], grip: [], air_temp_min: null, air_temp_max: null, track_temp_min: null, track_temp_max: null }

describe('ConditionsPoolForm', () => {
  it('sends the comma lists and the ranges', async () => {
    const calls = mockApi({
      'GET /api/seasons/4/conditions-pool': () => json(200, EMPTY),
      'PUT /api/seasons/4/conditions-pool': () => json(200, { ...EMPTY, weather: ['Despejado', 'Nublado'] }),
    })
    renderPage(<ConditionsPoolForm seasonId={4} />, { path: '/seasons/:id', url: '/seasons/4', me: ADMIN })
    await screen.findByText('Pool de condiciones para sortear')
    await userEvent.type(screen.getByLabelText('Clima'), 'Despejado, Nublado ,')
    await userEvent.type(screen.getByLabelText('Aire mín. °C'), '18')
    await userEvent.type(screen.getByLabelText('Aire máx. °C'), '26')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    const put = await vi.waitFor(() => calls.find((c) => c.key === 'PUT /api/seasons/4/conditions-pool')!)
    expect(put.body).toMatchObject({ weather: ['Despejado', 'Nublado'], air_temp_min: 18, air_temp_max: 26, grip: [] })
  })
})

describe('DrawHistory', () => {
  it('lists every draw with its reason', async () => {
    mockApi({
      'GET /api/rounds/9/conditions-draws': () =>
        json(200, [
          { values: { weather: 'Lluvia', air_temp_c: 20 }, reason: '', drawn_by: 'admin', drawn_at: '2026-10-12T10:00:00Z' },
          { values: { weather: 'Despejado', air_temp_c: 22 }, reason: 'Lluvia no corresponde', drawn_by: 'admin', drawn_at: '2026-10-12T11:00:00Z' },
        ]),
    })
    renderPage(<DrawHistory roundId={9} />, { path: '/rounds/:id', url: '/rounds/9', me: ADMIN })
    await userEvent.click(await screen.findByText('2 sorteos'))
    expect(screen.getByText(/Despejado · 22 \(Lluvia no corresponde\)/)).toBeInTheDocument()
  })
})
