import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { ReportSection } from './ReportSection'

afterEach(() => vi.restoreAllMocks())

const report = (id: number, number: number, extra = {}) => ({
  id, number, status: 'ready', language: 'es', tone: 'friendly', model: 'anthropic/claude-sonnet-5-5',
  prompt_version: 'race-1', source_version: 2, result_status: 'official',
  created_at: '2026-10-12T10:00:00Z', generated_at: '2026-10-12T10:01:00Z',
  text: 'Driver 1 ganó.\n\nEl reinicio sigue pendiente.', unread: true, error: null, facts: null, ...extra,
})

const page = { path: '/rounds/:roundId', url: '/rounds/9' }

describe('ReportSection', () => {
  it('shows NEW until the driver opens the report', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/reports': () =>
        json(200, { can_generate: false, ai_configured: false, reports: [report(5, 2), report(4, 1, { unread: false, text: 'Primera versión.' })] }),
      'POST /api/reports/5/read': () => json(200, { ok: true }),
    })
    renderPage(<ReportSection roundId={9} adminView={false} />, page)
    expect(await screen.findByText('Nuevo')).toBeInTheDocument()
    expect(screen.getByText('Versiones anteriores (1)')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Reporte 2'))
    expect(await screen.findByText('El reinicio sigue pendiente.')).toBeVisible()
    await vi.waitFor(() => expect(screen.queryByText('Nuevo')).not.toBeInTheDocument())
    expect(calls.some((c) => c.key === 'POST /api/reports/5/read')).toBe(true)
    expect(screen.queryByRole('button', { name: 'Generar' })).not.toBeInTheDocument()
  })

  it('lets an admin ask for a report and shows a failed one', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/reports': () =>
        json(200, {
          can_generate: true,
          ai_configured: false,
          reports: [report(6, 1, { status: 'failed', text: '', unread: false, error: 'ai_not_configured' })],
        }),
      'POST /api/rounds/9/reports': () => json(200, { can_generate: true, ai_configured: false, reports: [] }),
    })
    renderPage(<ReportSection roundId={9} adminView />, page)
    expect(await screen.findByText(/La IA no tiene clave/)).toBeInTheDocument()
    expect(screen.getByText(/ai_not_configured/)).toBeInTheDocument()
    expect(screen.getByText('Todavía no hay reporte.')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Tono'), 'roast')
    await userEvent.click(screen.getByRole('button', { name: 'Generar' }))
    await vi.waitFor(() =>
      expect(calls.find((c) => c.key === 'POST /api/rounds/9/reports')!.body).toEqual({ language: 'es', tone: 'roast' }),
    )
  })
})
