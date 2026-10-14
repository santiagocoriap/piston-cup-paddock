import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { IncidentsSection } from './IncidentsSection'

afterEach(() => vi.restoreAllMocks())

const incident = (key: number, cars: string[], kind: string, attempt: number, review: unknown = null) => ({
  key, started_at: '2026-10-11T22:31:00Z', kind, attempt, lap: 1, cars, max_speed: kind === 'env' ? 150 : 70,
  x: key * 10, z: key * 5,
  events: [{ id: key, at: '2026-10-11T22:31:00Z', kind: `collision_${kind}`, car: cars[0], other: cars[1] ?? null, speed_kmh: 70 }],
  review,
})

const data = (reviewed = false) => ({
  session: 'race', gap_seconds: 3, has_events: true, can_review: true,
  incidents: [
    incident(1, ['Driver 1', 'Driver 2'], 'car', 1, reviewed ? { outcome: 'racing_incident', note: 'Largada', reviewed_by: 'steward', reviewed_at: '2026-10-12T10:00:00Z' } : null),
    incident(2, ['Driver 2'], 'env', 2),
  ],
})

const page = { path: '/rounds/:roundId', url: '/rounds/9' }

describe('IncidentsSection', () => {
  it('filters the map and opens a marker with its events and review', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/incidents': () => json(200, data()),
      'PUT /api/rounds/9/incidents/1/review': () => json(200, data(true)),
    })
    renderPage(<IncidentsSection roundId={9} />, page)
    expect(await screen.findByRole('img', { name: 'Mapa de incidentes' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Largada \d · vuelta 1/ })).toHaveLength(2)

    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'env')
    expect(screen.getAllByRole('button', { name: /Largada \d · vuelta 1/ })).toHaveLength(1)
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), '')

    await userEvent.click(screen.getByRole('button', { name: 'Driver 1 + Driver 2' }))
    expect(screen.getByRole('region', { name: 'Eventos del incidente' })).toHaveTextContent('Driver 1 ↔ Driver 2')
    await userEvent.selectOptions(screen.getByLabelText('Revisión', { selector: 'form select' }), 'racing_incident')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
    expect(await screen.findByText(/Incidente de carrera — Largada/)).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'PUT /api/rounds/9/incidents/1/review')!.body).toEqual({ outcome: 'racing_incident', note: '' })
  })

  it('says why the tab is empty without collector events', async () => {
    mockApi({ 'GET /api/rounds/9/incidents': () => json(200, { ...data(), has_events: false, incidents: [] }) })
    renderPage(<IncidentsSection roundId={9} />, page)
    expect(await screen.findByText('Sin datos del colector')).toBeInTheDocument()
  })
})
