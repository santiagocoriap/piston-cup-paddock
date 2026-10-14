import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, DRIVER, json, mockApi, renderPage } from '../test-utils'
import { RecordsPage } from './RecordsPage'

afterEach(() => vi.restoreAllMocks())

const lap = (id: number, driver: string, time: number, reason: string | null = null) => ({
  lap_id: id, lap_time_ms: time, driver_name: driver, date: '2026-10-11T22:00:00Z', round_id: 1,
  round_number: 1, season_name: '2026', championship_name: 'LMDh', lap_number: 3,
  sectors_ms: [70968, 52627, 67118], tyre: 'M', ballast_kg: 8, restrictor: 0, conditions: {},
  source_file: 'RACE.json', uploaded_by: 'santi', ineligible_reason: reason, can_invalidate: false,
})

const data = {
  layouts: [{ id: 1, name: 'Highlands · Long' }],
  cars: [{ id: 1, name: 'Acura' }],
  classes: [],
  seasons: [{ id: 4, name: 'LMDh 2026' }],
  boards: [
    {
      layout_id: 1, track_name: 'Highlands', layout_name: 'Long', car_id: 1, car_name: 'Acura',
      category: 'race', record_ms: 189296,
      holders: [lap(1, 'Ana', 189296), lap(2, 'Juan', 189296)],
      history: [
        { kind: 'record', lap: lap(1, 'Ana', 189296) },
        { kind: 'equal', lap: lap(2, 'Juan', 189296) },
        { kind: 'removed', lap: lap(3, 'Martín', 188000, 'dsq') },
      ],
      ranking: [lap(1, 'Ana', 189296), lap(2, 'Juan', 189296), lap(4, 'Pedro Gómez', 190500)],
    },
  ],
}

describe('RecordsPage', () => {
  it('shows the record time, the shared holders, and unknown conditions', async () => {
    mockApi({ 'GET /api/records': () => json(200, data) })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    const board = await screen.findByRole('article', { name: /Récord de carrera: Highlands · Long · Acura/ })
    expect(board.querySelector('.record-time')).toHaveTextContent('3:09.296')
    expect(within(board).getByText('Récord compartido')).toBeInTheDocument()
    expect(within(board).getAllByText('Desconocidas')).toHaveLength(2)
    expect(within(board).getAllByText('8 kg / 0 %')).toHaveLength(2)
  })

  it('keeps a removed lap in the history with its reason', async () => {
    mockApi({ 'GET /api/records': () => json(200, data) })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    expect(await screen.findByText(/Ya no cuenta \(piloto descalificado\)/)).toBeInTheDocument()
  })

  it('says when there are no records', async () => {
    mockApi({ 'GET /api/records': () => json(200, { layouts: [], cars: [], classes: [], seasons: [], boards: [] }) })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    expect(await screen.findByText(/Todavía no hay récords/)).toBeInTheDocument()
  })

  it('ranks the best laps with the gap to the record', async () => {
    mockApi({ 'GET /api/records': () => json(200, data) })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    const table = await screen.findByRole('table', { name: 'Mejores vueltas' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((row) => row.className)).toEqual(['medal-1', 'medal-2', 'medal-3'])
    expect(rows[2]).toHaveTextContent('PGPedro Gómez3:10.500+1.204')
  })
})

describe('RecordsPage add record', () => {
  it('opens the form in a dialog from the header', async () => {
    mockApi({
      'GET /api/records': () => json(200, data),
      'GET /api/championships': () => json(200, [{ id: 1, name: 'Demo LMDh', can_manage: true }]),
      'GET /api/catalog/tracks': () => json(200, []),
      'GET /api/catalog/cars': () => json(200, []),
    })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: ADMIN })
    await userEvent.click(await screen.findByRole('button', { name: 'Agregar récord' }))
    const dialog = screen.getByRole('dialog', { name: 'Agregar récord histórico' })
    expect(dialog).toHaveAttribute('open')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cerrar' }))
    expect(dialog).not.toHaveAttribute('open')
  })

  it('does not show the add button to a driver', async () => {
    mockApi({ 'GET /api/records': () => json(200, data) })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    await screen.findByRole('table')
    expect(screen.queryByRole('button', { name: 'Agregar récord' })).not.toBeInTheDocument()
  })
})

describe('RecordsPage filters', () => {
  it('asks for the overall race board', async () => {
    const queries: string[] = []
    mockApi({
      'GET /api/records': (request) => {
        queries.push(new URL(request.url).search)
        return json(200, { layouts: [], cars: [], classes: [], seasons: [], boards: [] })
      },
    })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    await userEvent.click(await screen.findByRole('radio', { name: 'Carrera' }))
    await userEvent.click(screen.getByRole('switch', { name: 'Récord absoluto (sin importar el auto)' }))
    await vi.waitFor(() => expect(queries.at(-1)).toBe('?category=race&overall=true'))
  })

  it('shows the active filters as chips that remove the filter', async () => {
    const queries: string[] = []
    mockApi({
      'GET /api/records': (request) => {
        queries.push(new URL(request.url).search)
        return json(200, { layouts: [], cars: [], classes: [], seasons: [], boards: [] })
      },
    })
    renderPage(<RecordsPage />, { path: '/records', url: '/records', me: DRIVER })
    await userEvent.click(await screen.findByRole('radio', { name: 'Clasificación' }))
    const chips = await screen.findByRole('list', { name: 'Filtros activos' })
    expect(chips).toHaveTextContent('Clasificación')
    expect(await screen.findByText('Ningún récord con estos filtros')).toBeInTheDocument()
    await userEvent.click(within(chips).getByRole('button', { name: 'Quitar el filtro Clasificación' }))
    await vi.waitFor(() => expect(queries.at(-1)).toBe(''))
    expect(screen.queryByRole('list', { name: 'Filtros activos' })).not.toBeInTheDocument()
  })
})
