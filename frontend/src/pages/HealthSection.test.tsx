import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { HealthSection } from './HealthSection'

afterEach(() => vi.restoreAllMocks())

const health = (failed: unknown[]) => ({
  collectors: [
    {
      id: 1, name: 'Servidor AC', status: 'stopped', last_seen_at: '2026-10-11T22:00:00Z', last_file_at: null, last_event_at: null,
      version: '1.4.1', latest_version: '1.5.0', queued_files: 2, last_error: 'Upload failed: HTTP 502',
      last_error_at: '2026-10-11T22:00:00Z',
    },
  ],
  rounds: [
    {
      id: 9, number: 1, season_name: '2026', track_name: 'Highlands', scheduled_at: '2026-10-11T22:00:00Z',
      problems: ['missing_sectors', 'partial_events', 'collector_stopped'],
      counts: { laps: 40, laps_without_sectors: 3, lap_events: 12 },
    },
  ],
  failed,
  unmatched_files: 2,
})

describe('HealthSection', () => {
  it('shows a different message for each problem and retries a failed report', async () => {
    const report = { kind: 'report', id: 5, label: '2026 R1', error: 'ai_timeout', at: null }
    const calls = mockApi({
      'GET /api/championships/2/health': () => json(200, health([report])),
      'POST /api/reports/5/retry': () => json(200, health([])),
    })
    renderPage(<HealthSection championshipId={2} />, { path: '/championships/:id', url: '/championships/2' })
    expect(await screen.findByText('detenido en horario de carrera')).toBeInTheDocument()
    expect(screen.getByText(/versión 1.4.1 · se actualiza a 1.5.0 al arrancar · 2 archivos esperando/)).toBeInTheDocument()
    expect(screen.getByText(/Último error .*: Upload failed: HTTP 502/)).toBeInTheDocument()
    expect(screen.getByText('3 vueltas no tienen sectores.')).toBeInTheDocument()
    expect(screen.getByText('Eventos parciales: 12 vueltas por UDP de 40 en el archivo.')).toBeInTheDocument()
    expect(screen.getByText(/El colector no mandó nada esa noche/)).toBeInTheDocument()
    expect(screen.getByText(/2 archivos esperan una fecha/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('No hay tareas fallidas.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/reports/5/retry')).toBe(true)
  })
})
