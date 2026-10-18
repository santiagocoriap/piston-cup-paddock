import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { RoundPage } from './RoundPage'

afterEach(() => vi.restoreAllMocks())

function round(canManage: boolean, result: unknown = null, extra: Record<string, unknown> = {}) {
  return {
    can_protest: false,
    briefing: { announced_conditions: {}, protest_window_minutes: 60, my_handicap: null },
    status: result ? 'provisional' : null,
    published_at: result ? '2026-10-19T02:00:00Z' : null,
    protest_deadline: result ? '2026-10-19T03:00:00Z' : null,
    protest_window_open: Boolean(result),
    approved_at: null,
    version: result ? 1 : null,
    versions: result ? [{ number: 1, kind: 'entry', reason: '', created_at: '2026-10-19T02:00:00Z', created_by: 'santi' }] : [],
    penalties: [],
    protests: [],
    handicap_checks: [],
    ...extra,
    id: 9,
    number: 1,
    season_id: 5,
    season_name: '2026',
    championship_name: 'LMDh',
    track_name: 'Highlands',
    layout_name: 'Long',
    scheduled_at: '2026-10-19T00:30:00Z',
    event_timezone: 'America/Argentina/Buenos_Aires',
    can_manage: canManage,
    capabilities: canManage ? ['penalties', 'records', 'reports', 'restarts', 'results'] : [],
    rules: { version: 1, points_by_position: [25, 18, 15], pole_bonus: 0, fastest_lap_bonus: 0 },
    entries: [
      { entry_id: 1, driver_id: 11, number: 93, driver_name: 'Bing', car_name: 'Acura' },
      { entry_id: 2, driver_id: 12, number: 7, driver_name: 'Vice', car_name: 'Vanwall' },
      { entry_id: 3, driver_id: 13, number: 3, driver_name: 'Billy', car_name: 'Cadillac' },
    ],
    result,
  }
}

const noRestarts = {
  'GET /api/rounds/9/penalty-logs': () =>
    json(200, {
      files: [], new_files: 0, logs: 0, final_log: null, starts: [], existing_restarts: 0, penalties: [],
      ignored_penalties: 0, invalid_laps: [], warnings: [],
    }),
  'GET /api/rounds/9/imports': () => json(200, []),
  'GET /api/rounds/9/restarts': () =>
    json(200, {
      attempts: [],
      restarts: [],
      summary: { total: 0, caused: [], pending_or_disputed: 0, racing_incident: 0, technical: 0, unknown: 0 },
    }),
}

/** The result form opens in a dialog from the "Administrar" menu. */
async function openResultForm() {
  await userEvent.click(await screen.findByRole('button', { name: 'Administrar' }))
  await userEvent.click(screen.getByRole('button', { name: 'Cargar resultado' }))
}

const show = (me = undefined as typeof DRIVER | undefined) =>
  renderPage(<RoundPage />, { path: '/rounds/:roundId', url: '/rounds/9', me })

describe('RoundPage', () => {
  it('shows the result with points and the DNF mark', async () => {
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () =>
        json(200, round(false, [
          { entry_id: 1, status: 'finished', position: 1, entered_status: 'finished', entered_position: 1, pole: false, fastest_lap: false, number: 93, driver_name: 'Bing', points: 25 },
          { entry_id: 2, status: 'dnf', position: 2, entered_status: 'dnf', entered_position: 2, pole: false, fastest_lap: false, number: 7, driver_name: 'Vice', points: 18 },
          { entry_id: 3, status: 'dns', position: null, entered_status: 'dns', entered_position: null, pole: false, fastest_lap: false, number: 3, driver_name: 'Billy', points: 0 },
        ])),
    })
    show(DRIVER)
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('row', { name: /Vice/ })).toHaveTextContent('DNF')
    expect(within(table).getByRole('row', { name: /Billy/ })).toHaveTextContent('DNS')
    expect(screen.queryByRole('button', { name: 'Guardar resultado' })).not.toBeInTheDocument()
  })

  it('shows laps, the gap, laps down, and incidents', async () => {
    const line = (entry_id: number, name: string, position: number, extra = {}) => ({
      entry_id, status: 'finished', position, entered_status: 'finished', entered_position: position, pole: false,
      fastest_lap: false, number: entry_id, driver_id: entry_id, driver_name: name, points: 10, ...extra,
    })
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () =>
        json(200, round(false, [
          line(1, 'Ana', 1, { laps: 10, total_ms: 1964444, incidents: 0 }),
          line(2, 'Beto', 2, { laps: 10, total_ms: 2090908, gap_ms: 126464, incidents: 1 }),
          line(3, 'Ceci', 3, { laps: 9, total_ms: 1900000, laps_down: 1, incidents: 2 }),
        ])),
    })
    show(DRIVER)
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('row', { name: /Ana/ })).toHaveTextContent('32:44.444')
    expect(within(table).getByRole('row', { name: /Beto/ })).toHaveTextContent('+126.464')
    expect(within(table).getByRole('row', { name: /Ceci/ })).toHaveTextContent('+1 vuelta')
    expect(within(table).getByRole('columnheader', { name: 'Incidentes' })).toBeInTheDocument()
  })

  it('lists drivers who raced with other handicap values', async () => {
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () =>
        json(200, round(false, null, {
          handicap_checks: [{ entry_id: 1, driver_name: 'Ana', assigned_kg: 10, assigned_pct: 0, observed_kg: 8, observed_pct: 0 }],
        })),
    })
    show(DRIVER)
    expect(await screen.findByText('Ana: asignado 10 kg y 0 %, corrió con 8 kg y 0 %.')).toBeInTheDocument()
  })

  it('sends only the drivers who took part, with their positions', async () => {
    const calls = mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () => json(200, round(true)),
      'PUT /api/rounds/9/result': () => json(200, round(true, [])),
    })
    show()
    await openResultForm()
    await userEvent.selectOptions(await screen.findByLabelText('Estado Bing'), 'finished')
    await userEvent.type(screen.getByLabelText('Pos. Bing'), '1')
    await userEvent.selectOptions(screen.getByLabelText('Estado Vice'), 'dnf')
    await userEvent.type(screen.getByLabelText('Pos. Vice'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar resultado' }))

    // The dialog closes after the save.
    await vi.waitFor(() => expect(screen.queryByLabelText('Estado Bing')).not.toBeInTheDocument())
    const put = calls.find((call) => call.key === 'PUT /api/rounds/9/result')!
    expect(put.body).toEqual({
      lines: [
        { entry_id: 1, status: 'finished', position: 1, pole: false, fastest_lap: false },
        { entry_id: 2, status: 'dnf', position: 2, pole: false, fastest_lap: false },
      ],
      reason: '',
    })
  })

  it('shows the rule that a result breaks', async () => {
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () => json(200, round(true)),
      'PUT /api/rounds/9/result': () => json(422, { detail: 'positions_not_continuous' }),
    })
    show()
    await openResultForm()
    await userEvent.selectOptions(await screen.findByLabelText('Estado Bing'), 'finished')
    await userEvent.type(screen.getByLabelText('Pos. Bing'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar resultado' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('sin huecos ni repetidas')
  })

  it('disables the position for DNS and DSQ', async () => {
    mockApi({ ...noRestarts, 'GET /api/rounds/9': () => json(200, round(true)) })
    show()
    await openResultForm()
    await userEvent.selectOptions(await screen.findByLabelText('Estado Bing'), 'dsq')
    expect(screen.getByLabelText('Pos. Bing')).toBeDisabled()
  })

  it('shows the state, the deadline, and a penalty mark', async () => {
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () =>
        json(200, round(false, [
          { entry_id: 2, status: 'finished', position: 1, entered_status: 'finished', entered_position: 2, pole: false, fastest_lap: false, number: 2, driver_name: 'Vice', points: 25 },
          { entry_id: 1, status: 'finished', position: 2, entered_status: 'finished', entered_position: 1, pole: false, fastest_lap: false, number: 1, driver_name: 'Bing', points: 18 },
        ], { penalties: [{ id: 4, entry_id: 1, driver_name: 'Bing', kind: 'positions', value: 1, reason: 'Corte', source: 'steward', attempt: 1, protest_id: null, created_by: 'santi', created_at: '2026-10-19T02:30:00Z' }] })),
    })
    show(DRIVER)
    // The header and the status banner both show the state.
    expect(await screen.findAllByText('Provisional')).toHaveLength(2)
    expect(screen.getByText(/Protestas hasta/)).toBeInTheDocument()
    const bing = screen.getAllByRole('row', { name: /Bing/ })[0]
    expect(within(bing).getByText('Sanción')).toHaveAttribute('title', 'Cargado: 1')
    expect(screen.getByText(/−1 posiciones/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aprobar como oficial' })).not.toBeInTheDocument()
  })

  it('lets an admin approve the result', async () => {
    const calls = mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () => json(200, round(true, [{ entry_id: 1, status: 'finished', position: 1, entered_status: 'finished', entered_position: 1, pole: false, fastest_lap: false, number: 1, driver_name: 'Bing', points: 25 }])),
      'POST /api/rounds/9/result/approve': () => json(200, round(true, [], { status: 'official' })),
    })
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Aprobar como oficial' }))
    expect(calls.some((call) => call.key === 'POST /api/rounds/9/result/approve')).toBe(true)
  })

  it('shows a steward only the penalty and restart tools', async () => {
    const line = { entry_id: 1, status: 'finished', position: 1, entered_status: 'finished', entered_position: 1, pole: false, fastest_lap: false, number: 1, driver_name: 'Bing', points: 25 }
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () => json(200, { ...round(false, [line]), capabilities: ['penalties', 'restarts'] }),
    })
    show({ ...DRIVER, can_admin: true })
    expect((await screen.findAllByText('Agregar sanción')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Aprobar como oficial' })).not.toBeInTheDocument()
    expect(screen.queryByText('Importar archivo de resultados')).not.toBeInTheDocument()
  })

  it('lets a driver send a protest inside the window', async () => {
    const calls = mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () => json(200, round(false, [{ entry_id: 1, status: 'finished', position: 1, entered_status: 'finished', entered_position: 1, pole: false, fastest_lap: false, number: 1, driver_name: 'Bing', points: 25 }], { can_protest: true })),
      'POST /api/rounds/9/protests': () => json(200, round(false, [], { can_protest: true })),
    })
    show(DRIVER)
    const form = await screen.findByRole('form', { name: 'Presentar protesta' })
    await userEvent.type(within(form).getByLabelText('Qué pasó'), 'Me chocó en la T1')
    await userEvent.click(within(form).getByLabelText('Vice'))
    await userEvent.click(within(form).getByRole('button', { name: 'Enviar protesta' }))
    const body = calls.find((call) => call.key === 'POST /api/rounds/9/protests')!.body
    expect(body).toEqual({ description: 'Me chocó en la T1', entry_ids: [2], lap: null })
  })

  it('shows the briefing with conditions and the own car', async () => {
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () =>
        json(200, round(false, null, {
          briefing: {
            announced_conditions: { time_of_day: '14:00', weather: 'Nublado', air_temp_c: 18, track_temp_c: null, grip: '', notes: '' },
            protest_window_minutes: 60,
            my_handicap: { entry_number: 7, car_name: 'Acura', ballast_kg: 10, restrictor_pct: 2, source: 'assigned' },
          },
        })),
    })
    show(DRIVER)
    const briefing = await screen.findByRole('region', { name: 'Briefing' })
    expect(within(briefing).getByText('Nublado')).toBeInTheDocument()
    expect(within(briefing).getByText('18 °C')).toBeInTheDocument()
    expect(within(briefing).queryByText('Temperatura de pista')).not.toBeInTheDocument()
    expect(within(briefing).getByText('10 kg · 2 %')).toBeInTheDocument()
    expect(within(briefing).getByText(/Plazo de protestas: 60 minutos/)).toBeInTheDocument()
  })

  it('shows what the server used and where it differs from the announcement', async () => {
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () =>
        json(200, round(false, null, {
          briefing: {
            announced_conditions: { time_of_day: '15:30', weather: 'Despejado', air_temp_c: 28, track_temp_c: 30, grip: '', notes: '' },
            protest_window_minutes: 60,
            my_handicap: null,
            server_conditions: {
              session_type: 'race', started_at: '2026-10-11T22:27:00Z', weather: '3_clear',
              air_temp_c: 20, track_temp_c: 31, time_of_day: '16:00', grip_pct: 89,
            },
            conditions_differ: ['air_temp'],
          },
        })),
    })
    show(DRIVER)
    const briefing = await screen.findByRole('region', { name: 'Briefing' })
    expect(within(briefing).getByText('En el servidor')).toBeInTheDocument()
    expect(within(briefing).getAllByText('Despejado')).toHaveLength(2)
    expect(within(briefing).getByText('20 °C')).toBeInTheDocument()
    expect(within(briefing).getByText('89 %')).toBeInTheDocument()
    expect(within(briefing).getByRole('status')).toHaveTextContent('No coincide con lo anunciado: temperatura del aire.')
  })

  it('opens the analysis in tabs and keeps the race tab first', async () => {
    const line = { entry_id: 1, status: 'finished', position: 1, entered_status: 'finished', entered_position: 1, pole: false, fastest_lap: false, number: 1, driver_name: 'Bing', points: 25 }
    mockApi({ ...noRestarts, 'GET /api/rounds/9': () => json(200, round(false, [line])) })
    show(DRIVER)
    const tabs = await screen.findByRole('navigation', { name: 'Secciones de la fecha' })
    expect(within(tabs).getByRole('button', { name: 'Carrera' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('table')).toBeInTheDocument()
    await userEvent.click(within(tabs).getByRole('button', { name: 'Reinicios' }))
    expect(within(tabs).getByRole('button', { name: 'Reinicios' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the podium, the winner, and a count on each tab with data', async () => {
    const line = (entry_id: number, position: number, driver_name: string, points: number) => ({
      entry_id, status: 'finished', position, entered_status: 'finished', entered_position: position,
      pole: false, fastest_lap: false, number: entry_id, driver_name, points,
    })
    mockApi({
      ...noRestarts,
      'GET /api/rounds/9': () => json(200, round(false, [line(1, 1, 'Bing', 25), line(2, 2, 'Vice', 18)])),
      'GET /api/rounds/9/tab-counts': () =>
        json(200, { laps: 40, incidents: 0, replay: 0, restarts: 3, telemetry: 0, reports: 1 }),
    })
    show(DRIVER)
    const podium = await screen.findByRole('list', { name: 'Podio' })
    expect(within(podium).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'VVice#2218 pts',
      'BBing#1125 pts',
    ])
    expect(screen.getByText('Ganó Bing')).toBeInTheDocument()
    const tabs = screen.getByRole('navigation', { name: 'Secciones de la fecha' })
    const restarts = within(tabs).getByRole('button', { name: 'Reinicios' })
    await vi.waitFor(() => expect(restarts).toHaveTextContent('Reinicios3'))
    expect(within(tabs).getByRole('button', { name: 'Incidentes' })).toHaveClass('empty')
  })

  it('puts the briefing first before the race and folds it after the result', async () => {
    mockApi({ ...noRestarts, 'GET /api/rounds/9': () => json(200, round(false)) })
    show(DRIVER)
    expect(await screen.findByRole('region', { name: 'Briefing' })).toBeInTheDocument()
    expect(screen.queryByText('Antes de la carrera: briefing y asistencia')).not.toBeInTheDocument()
  })
})
