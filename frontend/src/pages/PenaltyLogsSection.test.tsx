import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { PenaltyLogsSection } from './PenaltyLogsSection'

afterEach(() => vi.restoreAllMocks())

const penalty = (key: string, kind: string, extra = {}) => ({
  key, kind, guid: '76561190000000003', name: 'Driver 03', entry_id: 2, driver_name: 'D2',
  penalty: 'Stop & go 5 seconds', cause: 'speed', lap: 4, seconds: 0, already: false, ...extra,
})

const logs = {
  files: [], new_files: 23, logs: 23, final_log: 'race_penalty_20261011_192731.log',
  starts: Array.from({ length: 20 }, (_, i) => ({ filename: `r${i}.log`, seconds: 60, new: true })),
  existing_restarts: 0,
  penalties: [penalty('a', 'served'), penalty('b', 'time', { seconds: 20, penalty: '' }), penalty('c', 'not_served')],
  ignored_penalties: 15,
  invalid_laps: [{ guid: 'g', name: 'Driver 05', lap_time_ms: 336531, lap_id: 7 }],
  warnings: [],
}

describe('PenaltyLogsSection', () => {
  it('shows the new restarts, the penalties, and applies the chosen ones', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/penalty-logs': () => json(200, logs),
      'POST /api/rounds/9/penalty-logs/apply': () =>
        json(200, { ...logs, starts: logs.starts.map((s) => ({ ...s, new: false })), existing_restarts: 20 }),
    })
    const onApplied = vi.fn()
    renderPage(<PenaltyLogsSection roundId={9} onApplied={onApplied} />, { path: '/rounds/:roundId', url: '/rounds/9' })
    expect(await screen.findByText('Se agregan 20 reinicios antes de la carrera que cuenta.')).toBeInTheDocument()
    expect(screen.getByText(/Se ignoran 15 líneas/)).toBeInTheDocument()
    expect(screen.getByText(/Revisá que el archivo de AC/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Sin cumplir/)).toBeDisabled()

    await userEvent.click(screen.getByLabelText(/Segundos al tiempo final/))
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar los logs' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Logs aplicados.')
    expect(calls.find((c) => c.key === 'POST /api/rounds/9/penalty-logs/apply')!.body).toEqual({
      penalty_keys: ['a'],
    })
    expect(onApplied).toHaveBeenCalled()
  })
})
