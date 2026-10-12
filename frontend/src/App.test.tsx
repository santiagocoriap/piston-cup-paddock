import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import { ADMIN, json, mockApi } from './test-utils'

afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('es')
})

const signedOut = {
  'GET /api/auth/me': () => json(401, { detail: 'Unauthorized' }),
  'GET /api/auth/csrf': () => new Response(null, { status: 204 }),
}

describe('App', () => {
  it('shows the login form in Spanish when nobody is signed in', async () => {
    mockApi(signedOut)
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument()
  })

  it('shows the championships after a correct login', async () => {
    mockApi({
      ...signedOut,
      'POST /api/auth/login': () => json(200, ADMIN),
      'GET /api/championships': () => json(200, []),
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Usuario'), 'santi')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'secret-pass')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('heading', { name: 'Campeonatos' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ligas' })).toBeInTheDocument()
  })

  it('shows an error after a wrong password', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/login': () => json(401, { detail: 'invalid_credentials' }) })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Usuario'), 'santi')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Usuario o contraseña incorrectos.')
  })

  it('uses the language of the signed-in user', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, { ...ADMIN, language: 'en' }),
      'GET /api/championships': () => json(200, []),
    })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Championships' })).toBeInTheDocument()
  })

  it('hides the admin links from a driver', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, { ...ADMIN, is_admin: false }),
      'GET /api/championships': () => json(200, []),
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Campeonatos' })
    expect(screen.queryByRole('link', { name: 'Ligas' })).not.toBeInTheDocument()
  })
})
