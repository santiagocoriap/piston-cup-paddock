import { expect, test, type Page } from '@playwright/test'
import { openAdminForm, signIn, submitForm } from './helpers'

async function api(page: Page, method: 'POST' | 'PUT', path: string, data: unknown) {
  const cookies = await page.context().cookies()
  const token = cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? ''
  const response = await page.request.fetch(`/api${path}`, {
    method,
    data,
    headers: { 'X-CSRFToken': token },
  })
  expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
  return response.json()
}

test('an admin fixes a track, runs a track vote, and the winners fill the calendar', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'One run is enough. The flow writes data.')
  await signIn(page)
  const run = Date.now().toString(36)

  // Setup: a three-round season and four tracks. The admin is also a driver in the championship.
  const me = await (await page.request.get('/api/auth/me')).json()
  const league = await api(page, 'POST', '/leagues', { name: `Vote ${run}` })
  const championship = await api(page, 'POST', `/leagues/${league.id}/championships`, { name: `V ${run}` })
  await api(page, 'PUT', `/championships/${championship.id}/members`, { user_id: me.id, role: 'driver' })
  const season = await api(page, 'POST', `/championships/${championship.id}/seasons`, {
    name: 'Vote 2026',
    planned_round_count: 3,
  })
  for (const name of ['Spa', 'Monza', 'Imola', 'Suzuka']) {
    const track = await api(page, 'POST', '/catalog/tracks', { key: `${name.toLowerCase()}_${run}`, name: `${name} ${run}` })
    await api(page, 'POST', `/catalog/tracks/${track.id}/layouts`, { key: '', name: 'GP' })
  }

  await page.getByRole('button', { name: 'Modo admin' }).click()
  await page.goto(`/seasons/${season.id}`)

  // A fixed track leaves two voted slots. The calendar forms open from the "Administrar" menu.
  await openAdminForm(page, 'calendar', 'Reservar pista fija')
  await submitForm(page, 'Reservar pista fija', {}, { 'Pista y trazado': `Spa ${run} · GP` })
  await expect(page.getByText('2 fechas libres para votar')).toBeVisible()

  // A track ballot with two choices for each driver. The first step of the form has these fields.
  await openAdminForm(page, 'ballots', 'Nueva votación')
  await submitForm(page, 'Nueva votación', { Título: `Pistas ${run}`, 'Opciones por piloto': '2' })
  await page.getByRole('link', { name: `Pistas ${run}` }).click()
  for (const name of ['Monza', 'Imola', 'Suzuka']) {
    await submitForm(page, 'Agregar opción', {}, { Pista: `${name} ${run} · GP` })
    await expect(page.getByText(`${name} ${run} - GP`).first()).toBeVisible()
  }
  await page.getByRole('button', { name: 'Abrir la votación' }).click()
  await expect(page.getByText('Abierta', { exact: true })).toBeVisible()

  // The admin votes as a driver, then closes the ballot.
  const voteForm = page.locator('fieldset.vote')
  await voteForm.getByLabel(new RegExp(`Monza ${run}`)).check()
  await voteForm.getByLabel(new RegExp(`Imola ${run}`)).check()
  await page.getByRole('button', { name: 'Votar' }).click()
  await expect(page.getByRole('status')).toHaveText('Tu voto quedó guardado.')
  await submitForm(page, 'Cerrar la votación', {})
  await expect(page.getByText('Decidida', { exact: true })).toBeVisible()

  // The calendar has the fixed track and the two winners.
  await page.getByRole('link', { name: 'Vote 2026' }).click()
  const calendar = page.locator('table').filter({ hasText: 'Origen' })
  await expect(calendar.getByRole('row').filter({ hasText: `Spa ${run}` })).toContainText('Fija')
  await expect(calendar.getByRole('row').filter({ hasText: `Monza ${run}` })).toContainText('Votada')
  await expect(calendar.getByRole('row').filter({ hasText: `Imola ${run}` })).toContainText('Votada')
  await expect(calendar.getByRole('row').filter({ hasText: `Suzuka ${run}` })).toHaveCount(0)
})
