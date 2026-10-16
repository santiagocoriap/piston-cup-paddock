import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { SeasonPage } from './SeasonPage'

afterEach(() => vi.restoreAllMocks())

function season(canManage: boolean) {
  return {
    id: 5,
    name: '2026',
    planned_round_count: 8,
    championship_id: 1,
    championship_name: 'LMDh',
    can_manage: canManage,
    entries: [
      { id: 1, driver_id: 3, driver_name: 'Bing', car_id: 2, car_name: 'Acura', number: 93, team: 'MSR' },
    ],
    rounds: [
      {
        id: 9,
        number: 1,
        track_layout_id: 4,
        track_name: 'Highlands',
        layout_name: 'Long',
        scheduled_at: '2026-10-19T00:30:00Z',
        origin: 'manual', cancelled: false, cancel_reason: '', track_changes: [],
      },
    ],
  }
}

const standings = {
  'GET /api/seasons/5/standings': () =>
    json(200, [
      {
        rank: 1, entry_id: 1, number: 93, driver_name: 'Bing', car_name: 'Acura', team: 'MSR',
        points: 25, wins: 1, rounds: [{ round_number: 1, status: 'finished', position: 1, points: 25 }],
      },
    ]),
}

const catalog = {
  'GET /api/catalog/tracks': () =>
    json(200, [{ id: 7, key: 'ks_highlands', name: 'Highlands', layouts: [{ id: 4, key: 'layout_long', name: 'Long' }] }]),
  'GET /api/catalog/cars': () => json(200, [{ id: 2, key: 'acura', name: 'Acura' }]),
  'GET /api/drivers': () => json(200, []),
}

const show = (me = undefined as typeof DRIVER | undefined) =>
  renderPage(<SeasonPage />, { path: '/seasons/:seasonId', url: '/seasons/5', me })

describe('SeasonPage', () => {
  it('lets the driver of an entry choose the skin, and nobody else', async () => {
    const mine = { ...season(false).entries[0], mine: true }
    const body = { ...season(false), entries: [mine, { ...mine, id: 2, driver_name: 'Rival', mine: false, number: 94 }] }
    const calls = mockApi({
      ...standings,
      ...catalog,
      'GET /api/seasons/5': () => json(200, body),
      'GET /api/entries/1/skins': () =>
        json(200, [
          { id: 10, key: '00_red', name: 'Rosso', team: '', number: '', has_preview: true },
          { id: 11, key: '01_blue', name: 'Azul', team: '', number: '', has_preview: false },
        ]),
      'PUT /api/entries/1/skin': () => json(200, { ...mine, skin_id: 11, skin_name: 'Azul' }),
    })
    show(DRIVER)
    const buttons = await screen.findAllByRole('button', { name: 'Elegir skin' })
    expect(buttons).toHaveLength(1) // The entry of the rival has no button.
    await userEvent.click(buttons[0])
    await userEvent.click(await screen.findByRole('radio', { name: 'Azul' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'PUT /api/entries/1/skin')).toBe(true))
    expect(calls.find((c) => c.key === 'PUT /api/entries/1/skin')?.body).toEqual({ skin_id: 11 })
  })

  it('shows the calendar with the manual origin and the entries', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)), ...standings })
    show(DRIVER)
    const link = await screen.findByRole('link', { name: 'Highlands · Long' })
    expect(link).toHaveAttribute('href', '/rounds/9')
    expect(link.closest('tr')).toHaveTextContent('Manual')
    expect(screen.getByText('MSR')).toBeInTheDocument()
  })

  it('shows a cancelled round and a replaced track', async () => {
    const data = season(false)
    Object.assign(data.rounds[0], {
      cancelled: true, cancel_reason: 'Servidor caído',
      track_changes: [{ old_layout: 'Spa · GP', new_layout: 'Highlands · Long', reason: 'Mod roto', changed_by: 'santi', changed_at: '2026-10-01T10:00:00Z' }],
    })
    mockApi({ 'GET /api/seasons/5': () => json(200, data), ...standings })
    show(DRIVER)
    const link = await screen.findByRole('link', { name: 'Highlands · Long' })
    expect(link.closest('tr')).toHaveTextContent('Cancelada')
    expect(link.closest('tr')).toHaveTextContent('Antes: Spa · GP (Mod roto)')
    expect(screen.queryByRole('button', { name: 'Cancelar fecha' })).not.toBeInTheDocument()
  })

  it('shows the standings with the points of each driver', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)), ...standings })
    show(DRIVER)
    expect(await screen.findByRole('heading', { name: 'Campeonato de pilotos' })).toBeInTheDocument()
    const standingsTable = (await screen.findAllByRole('table'))[0]
    const row = within(standingsTable).getByRole('row', { name: /Bing/ })
    expect(within(row).getByText('25')).toBeInTheDocument()
  })

  it('hides the forms from an admin in the driver mode', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(true)), ...standings })
    renderPage(<SeasonPage />, { path: '/seasons/:seasonId', url: '/seasons/5', mode: 'driver' })
    await screen.findAllByRole('table')
    expect(screen.queryByRole('button', { name: 'Administrar' })).not.toBeInTheDocument()
  })

  it('hides the forms from a driver', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)), ...standings })
    show(DRIVER)
    await screen.findAllByRole('table')
    expect(screen.queryByRole('button', { name: 'Administrar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Inscribir piloto' })).not.toBeInTheDocument()
  })

  it('puts the calendar and the 3 exports in one download menu', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)), ...standings })
    show(DRIVER)
    await userEvent.click(await screen.findByRole('button', { name: 'Descargar' }))
    expect(screen.getByRole('link', { name: 'Calendario (.ics)' })).toHaveAttribute('href', '/api/seasons/5/calendar.ics')
    expect(screen.getByRole('link', { name: 'Reinicios (CSV)' })).toHaveAttribute(
      'href',
      '/api/seasons/5/export/restarts.csv',
    )
  })

  it('highlights the clicked section, also the second one of a row', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)), ...standings })
    show(DRIVER)
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la temporada' })
    await userEvent.click(within(nav).getByRole('link', { name: 'Seguridad' }))
    expect(within(nav).getByRole('link', { name: 'Seguridad' })).toHaveAttribute('aria-current', 'location')
    expect(within(nav).getByRole('link', { name: 'Pelea por el título' })).not.toHaveAttribute('aria-current')
  })

  it('marks the next round with a status for screen readers', async () => {
    mockApi({ 'GET /api/seasons/5': () => json(200, season(false)), ...standings })
    show(DRIVER)
    const link = await screen.findByRole('link', { name: 'Highlands · Long' })
    expect(link.closest('tr')).toHaveTextContent('Próxima')
  })

  it('sends a new round with the timezone of the browser', async () => {
    const calls = mockApi({
      'GET /api/seasons/5': () => json(200, season(true)),
      ...standings,
      'POST /api/seasons/5/rounds': () => json(201, season(true).rounds[0]),
      ...catalog,
    })
    show()
    const calendar = (await screen.findByRole('heading', { name: 'Calendario' })).closest('section')!
    await userEvent.click(within(calendar).getByRole('button', { name: 'Administrar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Agregar fecha' }))
    const form = await screen.findByRole('form', { name: 'Agregar fecha' })
    await within(form).findByRole('option', { name: 'Highlands · Long' }) // Wait for the list.
    await userEvent.selectOptions(await within(form).findByLabelText('Pista y trazado'), '4')
    await userEvent.type(within(form).getByLabelText('Día y hora'), '2026-10-18T21:30')
    await userEvent.click(within(form).getByRole('button', { name: 'Agregar' }))
    const body = calls.find((call) => call.key === 'POST /api/seasons/5/rounds')!.body as {
      track_layout_id: number
      scheduled_at: string
    }
    expect(body.track_layout_id).toBe(4)
    expect(body.scheduled_at).toMatch(
      /^2026-10-18T21:30:00[+-]\d{2}:\d{2}$/,
    )
  })

  it('shows the API error when a number is taken', async () => {
    mockApi({
      'GET /api/seasons/5': () => json(200, season(true)),
      ...standings,
      'POST /api/seasons/5/entries': () => json(409, { detail: 'entry_exists' }),
      ...catalog,
      'GET /api/drivers': () => json(200, [{ id: 99, display_name: 'Bing', steam_guid: null, user_id: null, username: null }]),
      'GET /api/seasons/5/teams': () => json(200, [{ id: 1, name: 'Rojo' }]),
    })
    show()
    const entries = (await screen.findByRole('heading', { name: 'Pilotos inscriptos' })).closest('section')!
    await userEvent.click(within(entries).getByRole('button', { name: 'Administrar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Inscribir piloto' }))
    const form = await screen.findByRole('form', { name: 'Inscribir piloto' })
    await within(form).findByRole('option', { name: 'Bing' }) // Wait for the list.
    await userEvent.selectOptions(await within(form).findByLabelText('Piloto'), '99')
    await userEvent.selectOptions(await within(form).findByLabelText('Auto'), '2')
    await userEvent.type(within(form).getByLabelText('Número'), '93')
    await userEvent.click(within(form).getByRole('button', { name: 'Agregar' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'Ese piloto o ese número ya está inscripto en la temporada.',
    )
  })
})
