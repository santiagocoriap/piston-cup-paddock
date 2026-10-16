import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi } from '../test-utils'
import { InvitePage } from './InvitePage'

beforeEach(() => window.history.replaceState(null, '', '/invite#abcdefghijklmnop'))
afterEach(() => vi.restoreAllMocks())

describe('InvitePage', () => {
  it('reads the token after # and sets the password', async () => {
    const calls = mockApi({
      'POST /api/auth/invite/check': () => json(200, { username: 'bing', purpose: 'invite' }),
      'GET /api/auth/csrf': () => new Response(null, { status: 204 }),
      'POST /api/auth/invite/accept': () => json(200, { username: 'bing' }),
    })
    const onSignedIn = vi.fn()
    render(<InvitePage onSignedIn={onSignedIn} />)
    expect(await screen.findByText(/Hola, bing/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Contraseña'), 'new-pass-1234')
    await userEvent.type(screen.getByLabelText('Repetí la contraseña'), 'new-pass-1234')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar y entrar' }))
    expect(onSignedIn).toHaveBeenCalled()
    expect(calls[0].body).toEqual({ token: 'abcdefghijklmnop' })
    expect(window.location.hash).toBe('')
  })

  it('says when the link does not work', async () => {
    mockApi({ 'POST /api/auth/invite/check': () => json(422, { detail: 'link_not_valid' }) })
    render(<InvitePage onSignedIn={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('ya se usó o venció')
    expect(screen.getByRole('link', { name: 'Ir a iniciar sesión' })).toHaveAttribute('href', '/')
  })

  it('shows the password rules from the server', async () => {
    mockApi({
      'POST /api/auth/invite/check': () => json(200, { username: 'bing', purpose: 'reset' }),
      'GET /api/auth/csrf': () => new Response(null, { status: 204 }),
      'POST /api/auth/invite/accept': () =>
        json(422, { detail: 'weak_password', messages: ['This password is too common.'] }),
    })
    render(<InvitePage onSignedIn={vi.fn()} />)
    expect(await screen.findByText(/Elegí una contraseña nueva/)).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Guardar y entrar' })
    await userEvent.type(screen.getByLabelText('Contraseña'), '12345678')
    await userEvent.type(screen.getByLabelText('Repetí la contraseña'), '12345678')
    expect(save).toBeDisabled() // Only numbers: the page stops it before the server.
    await userEvent.clear(screen.getByLabelText('Contraseña'))
    await userEvent.clear(screen.getByLabelText('Repetí la contraseña'))
    await userEvent.type(screen.getByLabelText('Contraseña'), 'password1')
    await userEvent.type(screen.getByLabelText('Repetí la contraseña'), 'password1')
    await userEvent.click(save)
    expect(await screen.findByRole('alert')).toHaveTextContent('too common')
  })
})
