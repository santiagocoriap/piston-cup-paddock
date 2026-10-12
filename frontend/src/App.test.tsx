import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'

const ME = { id: 1, username: 'santi', language: 'es', is_admin: true }

function json(status: number, body?: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mockApi(routes: Record<string, () => Response>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const request = input as Request
    const key = `${request.method} ${new URL(request.url).pathname}`
    const handler = routes[key]
    if (!handler) throw new Error(`No mock for ${key}`)
    return handler()
  })
}

afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('es')
})

describe('App', () => {
  it('shows the login form in Spanish when nobody is signed in', async () => {
    mockApi({ 'GET /api/auth/me': () => json(401, { detail: 'Unauthorized' }) })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument()
  })

  it('shows the home page after a correct login', async () => {
    mockApi({
      'GET /api/auth/me': () => json(401, { detail: 'Unauthorized' }),
      'GET /api/auth/csrf': () => new Response(null, { status: 204 }),
      'POST /api/auth/login': () => json(200, ME),
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Usuario'), 'santi')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'secret-pass')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('heading', { name: 'Bienvenido, santi' })).toBeInTheDocument()
  })

  it('shows an error after a wrong password', async () => {
    mockApi({
      'GET /api/auth/me': () => json(401, { detail: 'Unauthorized' }),
      'GET /api/auth/csrf': () => new Response(null, { status: 204 }),
      'POST /api/auth/login': () => json(401, { detail: 'invalid_credentials' }),
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Usuario'), 'santi')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Usuario o contraseña incorrectos.')
  })

  it('uses the language of the signed-in user', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, { ...ME, language: 'en' }) })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Welcome, santi' })).toBeInTheDocument()
  })
})
