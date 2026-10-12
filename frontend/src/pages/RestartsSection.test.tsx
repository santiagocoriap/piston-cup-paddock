import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { RestartsSection } from './RestartsSection'

afterEach(() => vi.restoreAllMocks())

const entries = [
  { entry_id: 1, driver_id: 11, number: 1, driver_name: 'Ana', car_name: 'Acura' },
  { entry_id: 2, driver_id: 12, number: 2, driver_name: 'Juan', car_name: 'Acura' },
  { entry_id: 3, driver_id: 13, number: 3, driver_name: 'Martín', car_name: 'Acura' },
]

const data = {
  attempts: [
    { number: 1, status: 'abandoned' },
    { number: 2, status: 'abandoned' },
    { number: 3, status: 'accepted' },
  ],
  restarts: [
    {
      id: 7, abandoned_attempt: 1, replacement_attempt: 2, lap: 1, elapsed_seconds: 40, location: 'T2',
      reason: 'first_lap_crash', explanation: '', requested_by: 'Ana', executed_by: null, logged_by: 'santi',
      responsibility: 'drivers', review_status: 'confirmed',
      responsible: [{ entry_id: 2, driver_name: 'Juan' }, { entry_id: 3, driver_name: 'Martín' }],
    },
    {
      id: 8, abandoned_attempt: 2, replacement_attempt: 3, lap: null, elapsed_seconds: null, location: '',
      reason: 'server_problem', explanation: '', requested_by: null, executed_by: null, logged_by: 'santi',
      responsibility: 'technical', review_status: 'confirmed', responsible: [],
    },
  ],
  summary: {
    total: 2,
    caused: [
      { entry_id: 2, driver_name: 'Juan', total: 1, shared: 1 },
      { entry_id: 3, driver_name: 'Martín', total: 1, shared: 1 },
    ],
    pending_or_disputed: 0, racing_incident: 0, technical: 1, unknown: 0,
  },
}

function show(adminView: boolean) {
  return renderPage(<RestartsSection roundId={9} entries={entries} adminView={adminView} />, {
    path: '/rounds/:roundId',
    url: '/rounds/9',
    me: adminView ? undefined : DRIVER,
  })
}

describe('RestartsSection', () => {
  it('shows the restart count, the attempts, and the shared label', async () => {
    mockApi({ 'GET /api/rounds/9/restarts': () => json(200, data) })
    show(false)
    expect(await screen.findByText('2 reinicios antes de la largada aceptada')).toBeInTheDocument()
    expect(screen.getByText('Largada 3: aceptada')).toBeInTheDocument()
    const row = screen.getByRole('row', { name: /Juan, Martín/ })
    expect(within(row).getByText('Compartida')).toBeInTheDocument()
    expect(screen.getAllByText('1 compartidos')).toHaveLength(2)
    expect(screen.getByText(/1 técnicos/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Registrar reinicio' })).not.toBeInTheDocument()
  })

  it('sends a new restart with the responsible drivers', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/restarts': () => json(200, { ...data, restarts: [], attempts: [], summary: { ...data.summary, total: 0, caused: [] } }),
      'POST /api/rounds/9/restarts': () => json(201, data),
    })
    show(true)
    const form = await screen.findByRole('form', { name: 'Registrar reinicio' })
    await userEvent.type(within(form).getByLabelText('Vuelta'), '1')
    await userEvent.type(within(form).getByLabelText('Lugar'), 'T2')
    await userEvent.selectOptions(within(form).getByLabelText('Lo pidió'), '11')
    await userEvent.selectOptions(within(form).getByLabelText('Responsabilidad'), 'drivers')
    await userEvent.click(within(form).getByLabelText('Martín'))
    await userEvent.click(within(form).getByRole('button', { name: 'Registrar reinicio' }))

    const body = calls.find((call) => call.key === 'POST /api/rounds/9/restarts')!.body
    expect(body).toMatchObject({
      lap: 1,
      location: 'T2',
      reason: 'first_lap_crash',
      requested_by_id: 11,
      executed_by_id: null,
      responsibility: 'drivers',
      driver_entry_ids: [3],
      review_status: 'pending',
    })
  })
})
