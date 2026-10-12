import { expect, test } from '@playwright/test'
import { E2E_ADMIN } from '../fixtures'
import { signIn } from './helpers'

test('an admin signs in, stays signed in after a reload, and signs out', async ({ page }) => {
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Campeonatos' })).toBeVisible()

  await page.reload()
  await expect(page.getByRole('heading', { name: 'Campeonatos' })).toBeVisible()

  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible()
})

test('a wrong password shows an error', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Usuario').fill(E2E_ADMIN.username)
  await page.getByLabel('Contraseña').fill('wrong-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('alert')).toHaveText('Usuario o contraseña incorrectos.')
})

test('the health check reports the database', async ({ request }) => {
  const response = await request.get('/api/health')
  expect(response.ok()).toBe(true)
  expect(await response.json()).toEqual({ status: 'ok', database: true })
})
