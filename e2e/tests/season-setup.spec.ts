import { expect, test } from '@playwright/test'
import { signIn, submitForm } from './helpers'

// Each run starts with an empty test database. global-teardown.ts deletes it after the run.
const run = Date.now().toString(36)
const names = {
  league: `Liga ${run}`,
  championship: `LMDh ${run}`,
  driver: `Piloto ${run}`,
  track: `Highlands ${run}`,
  car: `Acura ${run}`,
}

test('an admin sets up a season without voting and enters a result', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'One run is enough. The flow writes data.')
  await signIn(page)
  await expect(page.getByRole('button', { name: 'Modo piloto' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('link', { name: 'Ligas' })).toBeHidden()
  await page.getByRole('button', { name: 'Modo admin' }).click()

  // League and championship
  await page.getByRole('link', { name: 'Ligas' }).click()
  await submitForm(page, 'Nueva liga', { Nombre: names.league })
  await expect(page.getByRole('listitem').filter({ hasText: names.league })).toBeVisible()
  await submitForm(page, 'Nuevo campeonato', { Nombre: names.championship }, { Liga: names.league })

  // A driver profile without an account
  await page.getByRole('link', { name: 'Pilotos' }).click()
  await submitForm(page, 'Nuevo piloto', { 'Nombre visible': names.driver })
  await expect(page.getByRole('row').filter({ hasText: names.driver })).toContainText('Sin cuenta')

  // Track, layout, and car
  await page.getByRole('link', { name: 'Pistas y autos' }).click()
  await submitForm(page, 'Nueva pista', { 'Carpeta en AC': `ks_highlands_${run}`, Nombre: names.track })
  await expect(page.getByText(names.track).first()).toBeVisible()
  await submitForm(
    page,
    'Nuevo trazado',
    { 'Carpeta en AC': 'layout_long', Nombre: 'Long' },
    { Pista: names.track },
  )
  await submitForm(page, 'Nuevo auto', { 'Carpeta en AC': `acura_${run}`, Nombre: names.car })
  await expect(page.getByText(names.car)).toBeVisible()

  // Season
  await page.getByRole('link', { name: 'Campeonatos' }).click()
  await page.getByRole('link', { name: names.championship }).click()
  await submitForm(page, 'Nueva temporada', {
    'Nombre de la temporada': '2026',
    'Carreras previstas': '8',
  })
  await page.getByRole('link', { name: '2026' }).click()
  await expect(page.getByText('8 carreras previstas')).toBeVisible()

  // Round and entry
  await submitForm(
    page,
    'Agregar fecha',
    { 'Día y hora': '2026-10-18T21:30' },
    { 'Pista y trazado': `${names.track} · Long` },
  )
  const round = page.getByRole('row').filter({ hasText: `${names.track} · Long` })
  await expect(round).toContainText('Manual')

  await submitForm(
    page,
    'Inscribir piloto',
    { Número: '93', Equipo: 'Meyer Shank' },
    { Piloto: names.driver, Auto: names.car },
  )
  await expect(page.getByRole('row').filter({ hasText: names.driver })).toContainText('Meyer Shank')

  // Result and standings
  await page.getByRole('link', { name: `${names.track} · Long` }).click()
  await expect(page.getByText('Todavía no hay resultado.')).toBeVisible()

  // A restart before the race that counts
  await submitForm(page, 'Registrar reinicio', { Vuelta: '1', Lugar: 'T1' })
  await expect(page.getByText('1 reinicio antes de la largada aceptada')).toBeVisible()
  await expect(page.getByText('Largada 2: en curso')).toBeVisible()
  await page.getByLabel(`Estado ${names.driver}`).selectOption('finished')
  await page.getByLabel(`Pos. ${names.driver}`).fill('1')
  await page.getByRole('button', { name: 'Guardar resultado' }).click()
  await expect(page.getByRole('status')).toContainText('Resultado guardado.')
  await expect(page.getByText('Largada 2: aceptada')).toBeVisible()
  await expect(page.getByText('Provisional', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Aprobar como oficial' }).click()
  await expect(page.getByText('Oficial', { exact: true })).toBeVisible()
  await expect(page.getByRole('table').first().getByRole('row', { name: new RegExp(names.driver) })).toContainText('25')

  await page.getByRole('link', { name: '2026' }).click()
  const standingsRow = page.getByRole('table').first().getByRole('row', { name: new RegExp(names.driver) })
  await expect(standingsRow).toContainText('25')

  // Audit trail
  await page.getByRole('link', { name: 'Historial' }).click()
  const resultEntry = page.getByRole('link', {
    name: `e2e-admin cargó el resultado de la fecha 1 (${names.track} - Long).`,
  })
  await expect(resultEntry).toBeVisible()
  await resultEntry.click()
  await expect(page.getByRole('heading', { name: /Fecha 1/ })).toBeVisible()
})
