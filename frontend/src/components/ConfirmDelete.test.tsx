import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { DangerMenu } from './DangerMenu'

afterEach(() => vi.restoreAllMocks())

describe('DangerMenu', () => {
  it('asks for the name of a season, then deletes it', async () => {
    const calls = mockApi({ 'DELETE /api/objects/season/7': () => json(200, { name: '2026' }) })
    const deleted = vi.fn()
    renderPage(<DangerMenu target={{ kind: 'season', id: 7, name: '2026' }} onDeleted={deleted} />, {
      path: '/',
      url: '/',
      me: ADMIN,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Más opciones de 2026' }))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar temporada' }))
    const confirm = screen.getByRole('button', { name: 'Borrar' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Para confirmar, escribí «2026»'), '2026')
    await userEvent.click(confirm)
    await vi.waitFor(() => expect(deleted).toHaveBeenCalled())
    expect(calls.some((c) => c.key === 'DELETE /api/objects/season/7')).toBe(true)
  })

  it('says where a track is in use', async () => {
    mockApi({
      'DELETE /api/objects/track/3': () => json(409, { detail: 'in_use', uses: ['round:Piston Cup 2026 R1'] }),
    })
    renderPage(<DangerMenu target={{ kind: 'track', id: 3, name: 'Spa' }} onDeleted={() => undefined} />, {
      path: '/',
      url: '/',
      me: ADMIN,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Más opciones de Spa' }))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar pista' }))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar' }))
    expect(await screen.findByText('No se puede borrar: está en uso.')).toBeInTheDocument()
    expect(screen.getByText('Fecha: Piston Cup 2026 R1')).toBeInTheDocument()
  })
})
