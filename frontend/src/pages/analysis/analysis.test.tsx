import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { BarChart, driverColor, LineChart } from './charts'
import { DriverAnalysis } from './DriverAnalysis'
import { RoundAnalysis } from './RoundAnalysis'
import { SeasonAnalysis } from './SeasonAnalysis'
import { cornerExits } from './TelemetryLab'

afterEach(() => vi.restoreAllMocks())

const spread = { count: 3, mean: 101000, median: 101000, trimmed: 101000, stdev: 1000, mad: 1000, q1: 100500, q3: 101500, low: 100000, high: 102000, outliers: [] }
const lap = (number: number, position: number, extra = {}) => ({
  number, ms: 100000 + number * 500, sectors_ms: [30000, 40000, 30000 + number * 500], valid: true, clean: number > 1, pit: null, contact: false, tyre: 'H',
  position, gap_to_leader_ms: position === 1 ? 0 : 1500, ahead_ms: position === 1 ? null : 1500, ...extra,
})
const driver = (id: number, name: string, finish: number) => ({
  entry_id: id, driver_id: id, name, number: id, grid: 3 - finish, finish, status: 'finished', points: 25 - finish, best_ms: 100500, best_lap: 1,
  theoretical_ms: 100000, best_sectors_ms: [30000, 40000, 30500], spread, battle: { attacking: 1, defending: 1, clean_air: 2 },
  laps: [lap(1, finish), lap(2, finish, { pit: 'in' }), lap(3, finish, { pit: 'out' }), lap(4, finish, { contact: true, fuel_left: 30, fuel_used: 2.5 })],
  stints: [{ start_lap: 1, end_lap: 2, tyre: 'H', laps: 2, median_ms: 100000, trend_ms: 50, pit_loss_ms: 21000 }, { start_lap: 3, end_lap: 4, tyre: 'M', laps: 2, median_ms: 100000, trend_ms: null, pit_loss_ms: null }],
  overtakes: 2 - finish, overtaken: finish - 1, attacks: 1, attacks_won: 1, defenses: 1, defenses_won: 0, battle_seconds: 120,
})
const round = {
  session: 'race', sessions: ['race', 'qualifying'], has_sectors: true, has_pit_data: true, clean_rules: ['invalid'], drivers: [driver(1, 'Ana', 1), driver(2, 'Bruno', 2)],
  has_positions: true, overtakes: [{ at_s: 100, lap: 2, attacker_id: 1, defender_id: 2, x: 10, z: 20 }],
}

const cell = (number: number, finish: number, extra = {}) => ({
  round_id: number, number, track: 'Laguna', grid: finish, finish, status: 'finished', points: 25 - finish, total_points: (25 - finish) * number, rank: finish,
  gap_to_leader: finish - 1, pole: finish === 1, fastest_lap: false, best_ms: 100000, median_ms: 101000, stdev_ms: 800, pace_pct: finish - 1, qualifying_pct: finish - 1, elo: 1500 + finish,
  overtakes: 1, attacks: 1, attacks_won: 1, defenses: 0, defenses_won: 0, incidents: 1, sectors_ms: [30000, 40000], ...extra,
})
const seasonDriver = (id: number, name: string, finish: number, rounds: number, extra = {}) => ({
  entry_id: id, driver_id: id, name, number: id, rank: finish, points: (25 - finish) * rounds, wins: finish === 1 ? rounds : 0, podiums: rounds, poles: 0, fastest_laps: 0, finishes: rounds, dnfs: 0,
  cells: Array.from({ length: rounds }, (_, i) => cell(i + 1, finish)),
  scores: { pace: 50, consistency: 50, qualifying: 50, results: 50, racecraft: 50, reliability: 50 }, average_pace_pct: finish - 1, average_stdev_ms: 800, max_points: 100, can_win: true,
  win_pct: null, expected_rank: null, rank_odds: null, pace_trend: null, pace_forecast: [], ...extra,
})
const season = (rounds: number) => ({
  season_id: 7, season_name: '2026', championship_name: 'Copa', planned_rounds: 8, remaining_rounds: 8 - rounds, points_by_position: [25, 18],
  rounds: Array.from({ length: rounds }, (_, i) => ({ id: i + 1, number: i + 1, track: 'Laguna', has_result: true, field_spread_pct: 1.5, circuit_type: 'mixed', corners: 8 })),
  rivalries: [{ a: 1, b: 2, battles: 3, seconds: 240, passes: 1 }],
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

describe('the new graphs', () => {
  const page = { path: '/', url: '/' }

  it('shows the overtakes, the battles, and the stops of a race', async () => {
    mockApi({
      'GET /api/rounds/5/analysis': () => json(200, round),
      'GET /api/rounds/5/track-map': () => json(200, { length_m: 1000, spline: [0, 0.5], x: [0, 100], z: [0, 100] }),
    })
    renderPage(<RoundAnalysis roundId={5} />, page)
    await userEvent.click(await screen.findByText('Duelos'))
    expect(screen.getByRole('heading', { name: 'Sobrepasos' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Mapa de sobrepasos' })).toBeInTheDocument()
    await userEvent.click(screen.getByText('Estrategia y neumáticos'))
    expect(screen.getByRole('heading', { name: 'Tiempo perdido en pits' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Consumo por vuelta' })).toBeInTheDocument()
  })

  it('says how to get the overtakes without collector positions', async () => {
    mockApi({
      'GET /api/rounds/5/analysis': () => json(200, { ...round, has_positions: false, overtakes: [] }),
      'GET /api/rounds/5/track-map': () => json(200, { length_m: null, spline: [], x: [], z: [] }),
    })
    renderPage(<RoundAnalysis roundId={5} />, page)
    await userEvent.click(await screen.findByText('Duelos'))
    expect(screen.getAllByText(/Sin posiciones del colector/).length).toBeGreaterThan(0)
  })

  it('draws the channels of a picked lap, and explains an old lap', async () => {
    const channels = { t_ms: [0, 100], pos: [0.1, 0.2], speed_kmh: [100, 110], gas: [1, 1], brake: [0, 0], steer: [1, 2], gear: [3, 3], rpm: [5000, 5100] }
    const row = { id: 9, driver_name: 'Ana', session_type: 'race', lap_number: 2, lap_time_ms: 100000, valid: true, access: 'full', attempt_number: 1 }
    mockApi({
      'GET /api/rounds/5/analysis': () => json(200, round),
      'GET /api/rounds/5/telemetry': () => json(200, [row]),
      'GET /api/rounds/5/track-map': () => json(200, { length_m: null, spline: [], x: [], z: [] }),
      'GET /api/telemetry-laps/9': () => json(200, { ...row, sample_hz: 20, car: 'x', channels }),
    })
    renderPage(<RoundAnalysis roundId={5} />, page)
    await userEvent.click(await screen.findByRole('tab', { name: 'Vueltas y sectores' }))
    await userEvent.click(screen.getByText('Fuerzas, neumáticos y línea'))
    await userEvent.selectOptions(await screen.findByLabelText(/Elegí hasta 3 vueltas/), '9')
    expect(await screen.findByRole('heading', { name: 'Diagrama G-G' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Suavidad del volante' })).toBeInTheDocument()
    expect(screen.getAllByText(/anteriores al script nuevo/).length).toBeGreaterThan(0)
  })

  it('changes the final points in the simulator', async () => {
    mockApi({ 'GET /api/seasons/7/analysis': () => json(200, season(2)) })
    renderPage(<SeasonAnalysis seasonId={7} />, page)
    await userEvent.click(await screen.findByText('Predicciones'))
    expect(screen.getByRole('heading', { name: 'Simulador de escenarios' })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Bruno'), '1')
    expect(screen.getAllByText(/\+150/).length).toBeGreaterThan(0) // 6 remaining rounds × 25 points.
  })
})

describe('cornerExits', () => {
  it('finds each low point of the speed, and reads the speed after it', () => {
    const fast = Array.from({ length: 200 }, () => 200)
    const corner = [...Array.from({ length: 20 }, (_, i) => 200 - i * 5), ...Array.from({ length: 200 }, (_, i) => Math.min(100 + i, 200))]
    const found = cornerExits([...fast, ...corner, ...fast])
    expect(found).toHaveLength(1)
    expect(found[0].later).toBeGreaterThan(found[0].exit)
  })

  it('finds nothing on a straight', () => {
    expect(cornerExits(Array.from({ length: 300 }, () => 200))).toEqual([])
  })
})
