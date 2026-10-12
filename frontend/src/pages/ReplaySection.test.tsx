import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { ReplaySection, positionAt } from './ReplaySection'

afterEach(() => vi.restoreAllMocks())

const ana = { key: 'g1', name: 'Ana', t_ms: [0, 200, 9000], x: [0, 10, 50], z: [0, 0, 0] }

describe('positionAt', () => {
  it('moves in a line between close samples and shows a gap between far samples', () => {
    expect(positionAt(ana, 100)).toEqual({ x: 5, z: 0 })
    expect(positionAt(ana, 200)).toEqual({ x: 10, z: 0 })
    expect(positionAt(ana, 4000)).toBeNull() // 8.8 s without samples: a gap.
    expect(positionAt(ana, 9500)).toBeNull() // After the last sample.
  })
})

describe('ReplaySection', () => {
  it('jumps to a marker and lists the cars without data', async () => {
    mockApi({
      'GET /api/rounds/9/replay': () =>
        json(200, {
          attempts: [{ number: 1, started_at: '2026-10-11T22:30:00Z' }, { number: 2, started_at: '2026-10-11T22:31:00Z' }],
          attempt: 1,
          has_positions: true,
          duration_ms: 60000,
          cars: [ana, { key: 'g2', name: 'Beto', t_ms: [0, 200], x: [5, 6], z: [5, 5] }],
          markers: [
            { t_ms: 4000, kind: 'incident', label: 'Ana + Beto', incident_key: 3 },
            { t_ms: 60000, kind: 'restart', label: '', incident_key: null },
          ],
        }),
    })
    renderPage(<ReplaySection roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9' })
    expect(await screen.findByRole('img', { name: 'Posiciones de los autos' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reproducir' })).toBeInTheDocument()
    expect(screen.getByLabelText('Largada')).toHaveValue('1')

    await userEvent.click(screen.getByRole('button', { name: 'Incidente: Ana + Beto' }))
    expect(screen.getByLabelText('Línea de tiempo')).toHaveValue('4000')
    expect(screen.getByText('Sin datos en este momento: Ana, Beto.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reinicio de la carrera' })).toBeInTheDocument()
  })
})
