import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
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
    await userEvent.selectOptions(await screen.findByLabelText('Sesión'), 'race')
    await userEvent.click(screen.getByLabelText('Récord absoluto (sin importar el auto)'))
    await vi.waitFor(() => expect(queries.at(-1)).toBe('?category=race&overall=true'))
  })
})
