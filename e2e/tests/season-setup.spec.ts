import { expect, test } from '@playwright/test'
import { signIn, submitForm } from './helpers'

// The local database keeps data between runs, so each run uses new names.
const run = Date.now().toString(36)
const names = {
  league: `Liga ${run}`,
  championship: `LMDh ${run}`,
  driver: `Piloto ${run}`,
  track: `Highlands ${run}`,
  car: `Acura ${run}`,
}

test('an admin sets up a season without voting', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'One run is enough. The flow writes data.')
  await signIn(page)

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
})
