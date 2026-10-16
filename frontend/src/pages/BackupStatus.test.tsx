import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { BackupStatus } from './BackupStatus'

afterEach(() => vi.restoreAllMocks())

const run = (status: string, extra = {}) => ({
  status, file_name: '', size_bytes: null, rows: null, files: null, error: '', started_by: 'santi',
  started_at: '2026-10-12T10:00:00Z', finished_at: null, ...extra,
})

describe('BackupStatus', () => {
  it('shows a failed backup and starts a new one', async () => {
    const calls = mockApi({
      'GET /api/backups/status': () =>
        json(200, { last: run('failed', { error: 'No space left on device' }), last_ok_at: '2026-10-10T10:00:00Z' }),
      'POST /api/backups': () => json(200, { last: run('running'), last_ok_at: '2026-10-10T10:00:00Z' }),
    })
    renderPage(<BackupStatus />, { path: '/championships/:id', url: '/championships/2', me: ADMIN })
    expect(await screen.findByText('falló')).toBeInTheDocument()
    expect(screen.getByText(/No space left on device/)).toBeInTheDocument()
    expect(screen.getByText(/Último backup correcto/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Hacer backup ahora' }))
    expect(await screen.findByText('en curso')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hacer backup ahora' })).toBeDisabled()
    expect(calls.some((c) => c.key === 'POST /api/backups')).toBe(true)
  })

  it('shows the size of a good backup', async () => {
    mockApi({
      'GET /api/backups/status': () =>
        json(200, {
          last: run('ok', { file_name: 'paddock.zip', size_bytes: 3 * 1024 * 1024, rows: 1200, files: 14, finished_at: '2026-10-12T10:01:00Z' }),
          last_ok_at: '2026-10-12T10:01:00Z',
        }),
    })
    renderPage(<BackupStatus />, { path: '/championships/:id', url: '/championships/2', me: ADMIN })
    expect(await screen.findByText(/3\.0 MB · 1200 filas, 14 archivos/)).toBeInTheDocument()
  })
})
