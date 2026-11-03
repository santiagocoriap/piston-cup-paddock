import { screen, within } from '@testing-library/react'
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

  it('gives the same review to all the marked incidents', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/incidents': () => json(200, data()),
      'PUT /api/rounds/9/incidents/review': () => json(200, data(true)),
    })
    renderPage(<IncidentsSection roundId={9} />, page)
    const group = await screen.findByRole('group', { name: 'Revisar varios incidentes' })
    expect(within(group).getByRole('button', { name: 'Aplicar a 0 incidentes' })).toBeDisabled()
    await userEvent.click(within(group).getByRole('checkbox', { name: 'Marcar todos los de la lista (2)' }))
    await userEvent.selectOptions(within(group).getByLabelText('Revisión'), 'racing_incident')
    await userEvent.type(within(group).getByLabelText('Nota'), 'Largada')
    await userEvent.click(within(group).getByRole('button', { name: 'Aplicar a 2 incidentes' }))
    await vi.waitFor(() =>
      expect(calls.find((c) => c.key === 'PUT /api/rounds/9/incidents/review')!.body).toEqual({ keys: [1, 2], outcome: 'racing_incident', note: 'Largada' }),
    )
    // After the save, nothing stays marked.
    expect(await within(group).findByRole('button', { name: 'Aplicar a 0 incidentes' })).toBeDisabled()
  })

  it('marks one incident and leaves out a marked incident that a filter hides', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/incidents': () => json(200, data()),
      'PUT /api/rounds/9/incidents/review': () => json(200, data()),
    })
    renderPage(<IncidentsSection roundId={9} />, page)
    await userEvent.click(await screen.findByRole('checkbox', { name: /Marcar el incidente de Driver 1/ }))
    await userEvent.click(screen.getByRole('checkbox', { name: /Marcar el incidente de Driver 2,/ }))
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'env')
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar a 1 incidente' }))
    await vi.waitFor(() => expect(calls.find((c) => c.key === 'PUT /api/rounds/9/incidents/review')!.body).toMatchObject({ keys: [2] }))
  })

  it('says why the tab is empty without collector events', async () => {
    mockApi({ 'GET /api/rounds/9/incidents': () => json(200, { ...data(), has_events: false, incidents: [] }) })
    renderPage(<IncidentsSection roundId={9} />, page)
    expect(await screen.findByText('Sin datos del colector')).toBeInTheDocument()
  })
})
