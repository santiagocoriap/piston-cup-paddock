import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { BarChart, driverColor, LineChart } from './charts'
import { DriverAnalysis } from './DriverAnalysis'
import { RoundAnalysis } from './RoundAnalysis'
import { SeasonAnalysis } from './SeasonAnalysis'

afterEach(() => vi.restoreAllMocks())

const spread = { count: 3, mean: 101000, median: 101000, trimmed: 101000, stdev: 1000, mad: 1000, q1: 100500, q3: 101500, low: 100000, high: 102000, outliers: [] }
const lap = (number: number, position: number, extra = {}) => ({
  number, ms: 100000 + number * 500, sectors_ms: [30000, 40000, 30000 + number * 500], valid: true, clean: number > 1, pit: null, contact: false, tyre: 'H',
  position, gap_to_leader_ms: position === 1 ? 0 : 1500, ahead_ms: position === 1 ? null : 1500, ...extra,
})
const driver = (id: number, name: string, finish: number) => ({
  entry_id: id, driver_id: id, name, number: id, grid: 3 - finish, finish, status: 'finished', points: 25 - finish, best_ms: 100500, best_lap: 1,
  theoretical_ms: 100000, best_sectors_ms: [30000, 40000, 30500], spread, battle: { attacking: 1, defending: 1, clean_air: 2 },
  laps: [lap(1, finish), lap(2, finish), lap(3, finish), lap(4, finish, { contact: true })],
})
const round = { session: 'race', sessions: ['race', 'qualifying'], has_sectors: true, has_pit_data: false, clean_rules: ['invalid'], drivers: [driver(1, 'Ana', 1), driver(2, 'Bruno', 2)] }

const cell = (number: number, finish: number, extra = {}) => ({
  round_id: number, number, track: 'Laguna', grid: finish, finish, status: 'finished', points: 25 - finish, total_points: (25 - finish) * number, rank: finish,
  gap_to_leader: finish - 1, pole: finish === 1, fastest_lap: false, best_ms: 100000, median_ms: 101000, stdev_ms: 800, pace_pct: finish - 1, qualifying_pct: finish - 1, elo: 1500 + finish, ...extra,
})
const seasonDriver = (id: number, name: string, finish: number, rounds: number, extra = {}) => ({
  entry_id: id, driver_id: id, name, number: id, rank: finish, points: (25 - finish) * rounds, wins: finish === 1 ? rounds : 0, podiums: rounds, poles: 0, fastest_laps: 0, finishes: rounds, dnfs: 0,
  cells: Array.from({ length: rounds }, (_, i) => cell(i + 1, finish)),
  scores: { pace: 50, consistency: 50, qualifying: 50, results: 50, racecraft: 50, reliability: 50 }, average_pace_pct: finish - 1, average_stdev_ms: 800, max_points: 100, can_win: true,
  win_pct: null, expected_rank: null, rank_odds: null, ...extra,
})
const season = (rounds: number) => ({
  season_id: 7, season_name: '2026', championship_name: 'Copa', planned_rounds: 8, remaining_rounds: 8 - rounds, points_by_position: [25, 18],
  rounds: Array.from({ length: rounds }, (_, i) => ({ id: i + 1, number: i + 1, track: 'Laguna', has_result: true, field_spread_pct: 1.5 })),
  drivers: [seasonDriver(1, 'Ana', 1, rounds), seasonDriver(2, 'Bruno', 2, rounds)],
})

describe('charts', () => {
  it('gives a driver the same color each time', () => {
    expect(driverColor(3)).toBe(driverColor(3))
    expect(driverColor(3)).not.toBe(driverColor(4))
  })

  it('shows an empty value as a dash, not as zero', () => {
    renderPage(<BarChart label="x" rows={[{ key: 1, label: 'Ana', value: null }]} />, { path: '/', url: '/' })
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('draws nothing without points', () => {
    const { container } = renderPage(<LineChart series={[]} xLabel="x" yLabel="y" />, { path: '/', url: '/' })
    expect(container.querySelector('svg.chart')).toBeNull()
  })
})

describe('RoundAnalysis', () => {
  it('shows the race graphs and says what needs more data', async () => {
    mockApi({ 'GET /api/rounds/5/analysis': () => json(200, round) })
    renderPage(<RoundAnalysis roundId={5} />, { path: '/', url: '/' })
    expect(await screen.findByRole('heading', { name: 'Posición por vuelta' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tiempos de vuelta' })).toBeInTheDocument()
    expect(screen.getByText('5 gráficos necesitan más datos')).toBeInTheDocument()
  })

  it('reads another session and hides the race graphs', async () => {
    const calls = mockApi({ 'GET /api/rounds/5/analysis': () => json(200, round) })
    renderPage(<RoundAnalysis roundId={5} />, { path: '/', url: '/' })
    await userEvent.selectOptions(await screen.findByLabelText('Sesión'), 'qualifying')
    await vi.waitFor(() => expect(calls.filter((c) => c.key === 'GET /api/rounds/5/analysis').length).toBe(2))
  })

  it('shows the laps and sectors view', async () => {
    mockApi({ 'GET /api/rounds/5/analysis': () => json(200, round) })
    renderPage(<RoundAnalysis roundId={5} />, { path: '/', url: '/' })
    await userEvent.click(await screen.findByRole('tab', { name: 'Vueltas y sectores' }))
    expect(screen.getByRole('heading', { name: 'Diferencia por sector' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Vuelta teórica' })).toBeInTheDocument()
  })

  it('hides a driver on all the graphs', async () => {
    mockApi({ 'GET /api/rounds/5/analysis': () => json(200, round) })
    renderPage(<RoundAnalysis roundId={5} />, { path: '/', url: '/' })
    await userEvent.click(await screen.findByRole('button', { name: 'Bruno' }))
    expect(screen.getByRole('button', { name: 'Bruno' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getAllByText('Hacen falta 2 pilotos con datos.').length).toBeGreaterThan(0)
  })
})

describe('SeasonAnalysis', () => {
  it('says that a season without results has no graphs', async () => {
    mockApi({ 'GET /api/seasons/7/analysis': () => json(200, { ...season(1), rounds: [{ ...season(1).rounds[0], has_result: false }] }) })
    renderPage(<SeasonAnalysis seasonId={7} />, { path: '/', url: '/' })
    expect(await screen.findByText('Todavía no hay resultados en esta temporada.')).toBeInTheDocument()
  })

  it('asks for more rounds instead of a graph with one point', async () => {
    mockApi({ 'GET /api/seasons/7/analysis': () => json(200, season(1)) })
    renderPage(<SeasonAnalysis seasonId={7} />, { path: '/', url: '/' })
    await screen.findByRole('heading', { name: 'Puntos acumulados' })
    expect(screen.getAllByText('Hacen falta al menos 2 fechas con resultado.').length).toBeGreaterThan(0)
  })

  it('shows the prediction as an estimate after enough rounds', async () => {
    const data = season(3)
    data.drivers = [seasonDriver(1, 'Ana', 1, 3, { win_pct: 80, expected_rank: 1.2, rank_odds: [80, 20] }), seasonDriver(2, 'Bruno', 2, 3, { win_pct: 20, expected_rank: 1.8, rank_odds: [20, 80] })]
    mockApi({ 'GET /api/seasons/7/analysis': () => json(200, data) })
    renderPage(<SeasonAnalysis seasonId={7} />, { path: '/', url: '/' })
    await userEvent.click(await screen.findByText('Predicciones'))
    expect(await screen.findByRole('heading', { name: 'Probabilidad de título' })).toBeInTheDocument()
    expect(screen.getByText(/Estimación, no un dato/)).toBeInTheDocument()
  })
})

describe('DriverAnalysis', () => {
  it('shows the profile and compares with a rival', async () => {
    mockApi({ 'GET /api/drivers/1/analysis': () => json(200, [season(2)]) })
    renderPage(<DriverAnalysis driverId={1} />, { path: '/', url: '/' })
    expect(await screen.findByRole('heading', { name: 'Perfil del piloto' })).toBeInTheDocument()
    expect(screen.getByLabelText('Rival')).toHaveValue('2')
    await userEvent.click(screen.getByText('Mano a mano'))
    expect(await screen.findByRole('heading', { name: 'Ana contra Bruno' })).toBeInTheDocument()
  })

  it('says that a driver has no results', async () => {
    mockApi({ 'GET /api/drivers/1/analysis': () => json(200, []) })
    renderPage(<DriverAnalysis driverId={1} />, { path: '/', url: '/' })
    expect(await screen.findByText('Este piloto todavía no tiene resultados.')).toBeInTheDocument()
  })
})
