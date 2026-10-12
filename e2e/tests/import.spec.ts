import { expect, test, type Page } from '@playwright/test'
import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { signIn } from './helpers'

const LOG_FOLDER = fileURLToPath(
  new URL('../../samples/2026-10-11-ks-highlands/realpenalty/', import.meta.url),
)
const RACE_FILE = fileURLToPath(
  new URL('../../samples/2026-10-11-ks-highlands/2026_10_11_20_7_RACE.json', import.meta.url),
)
// The five drivers with laps in the sample race, in finishing order.
const DRIVERS = [
  ['Driver 01', '76561190000000001'],
  ['Driver 03', '76561190000000003'],
  ['Driver 06', '76561190000000006'],
  ['Driver 05', '76561190000000005'],
  ['Driver 04', '76561190000000004'],
]

/** Call the API with the session and the CSRF token of the signed-in page. */
async function apiPost(page: Page, path: string, data: unknown) {
  const cookies = await page.context().cookies()
  const token = cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post(`/api${path}`, {
    data,
    headers: { 'X-CSRFToken': token },
  })
  expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
  return response.json()
}

test('an admin imports a real AC result file and applies it', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'One run is enough. The flow writes data.')
  await signIn(page)
  const run = Date.now().toString(36)

  const league = await apiPost(page, '/leagues', { name: `Import ${run}` })
  const championship = await apiPost(page, `/leagues/${league.id}/championships`, { name: `Imp ${run}` })
  const season = await apiPost(page, `/championships/${championship.id}/seasons`, {
    name: 'Import 2026',
    planned_round_count: 1,
  })
  const track = await apiPost(page, '/catalog/tracks', { key: 'ks_highlands', name: 'Highlands' })
  const layout = await apiPost(page, `/catalog/tracks/${track.id}/layouts`, {
    key: 'layout_long',
    name: 'Long',
  })
  const car = await apiPost(page, '/catalog/cars', { key: 'trr_lmdh_acura_arx-06', name: 'Acura' })
  for (const [index, [name, guid]] of DRIVERS.entries()) {
    const driver = await apiPost(page, '/drivers', { display_name: name, steam_guid: guid })
    await apiPost(page, `/seasons/${season.id}/entries`, {
      driver_id: driver.id,
      car_id: car.id,
      number: index + 1,
    })
  }
  const round = await apiPost(page, `/seasons/${season.id}/rounds`, {
    track_layout_id: layout.id,
    scheduled_at: '2026-10-11T22:00:00Z',
  })

  await page.getByRole('button', { name: 'Modo admin' }).click()
  await page.goto(`/rounds/${round.id}`)
  await page.getByLabel('Archivo de resultados', { exact: true }).setInputFiles(RACE_FILE)
  await page.getByRole('form', { name: 'Importar archivo de resultados' }).getByRole('button', { name: 'Subir y revisar' }).click()

  const preview = page.getByRole('region', { name: 'Revisión del archivo' })
  await expect(preview.getByText(/Se aplica a la largada 1/)).toBeVisible()
  await expect(preview.getByRole('row', { name: /Driver 01/ })).toContainText('3:09.296')
  await preview.getByLabel('Estado final Driver 04').selectOption('dnf')
  await preview.getByRole('button', { name: 'Aplicar el archivo' }).click()
  await expect(preview.getByText('Archivo aplicado.')).toBeVisible()

  const result = page.getByRole('table').first()
  await expect(result.getByRole('row', { name: /Driver 01/ })).toContainText('25')
  await expect(result.getByRole('row', { name: /Driver 04/ })).toContainText('DNF')

  // The Real Penalty logs of the night add the 20 abandoned starts as restarts.
  const logFiles = readdirSync(LOG_FOLDER).filter((name) => name.endsWith('.log')).map((name) => join(LOG_FOLDER, name))
  await page.getByLabel('Logs de Real Penalty', { exact: true }).setInputFiles(logFiles)
  await page.getByRole('form', { name: 'Importar logs de Real Penalty' }).getByRole('button', { name: 'Subir y revisar' }).click()
  await expect(page.getByText('Se agregan 20 reinicios antes de la carrera que cuenta.')).toBeVisible()
  await page.getByRole('button', { name: 'Aplicar los logs' }).click()
  await expect(page.getByText('Logs aplicados.')).toBeVisible()
  await expect(page.getByText('20 reinicios antes de la largada aceptada')).toBeVisible()

  // The lap tables mark best laps and show the pit laps from the logs.
  const laps = page.getByRole('region', { name: 'Vueltas' })
  await expect(laps.getByRole('img', { name: 'Tiempo de vuelta por vuelta' })).toBeVisible()
  await expect(laps.getByText('Teórica').first()).toBeVisible()
  await laps.getByText(/Driver 06 · \d+ vueltas/).click()
  await expect(laps.getByRole('table', { name: 'Vueltas de Driver 06' }).getByText('Salida')).toBeVisible()

  // The worker writes the race report. Without an AI key it fails, and the results stay.
  await page.getByRole('form', { name: 'Generar reporte' }).getByRole('button', { name: 'Generar' }).click()
  await expect(page.getByText(/Reporte 1 · (Falló|Listo)/)).toBeVisible({ timeout: 30_000 })

  // The same file again adds nothing.
  await page.getByLabel('Archivo de resultados', { exact: true }).setInputFiles(RACE_FILE)
  await page.getByRole('form', { name: 'Importar archivo de resultados' }).getByRole('button', { name: 'Subir y revisar' }).click()
  await expect(page.getByText('Este archivo ya estaba subido. No se agregó nada.')).toBeVisible()

  // The winner carries the first win step into the next round.
  await page.goto(`/seasons/${season.id}`)
  const handicapRow = page.locator('table.handicaps tr').filter({ hasText: 'Driver 01' })
  await expect(page.getByRole('heading', { name: 'Pelea por el título' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Reporte de la temporada' })).toBeVisible()
  await expect(handicapRow).toContainText('10 kg · 2 %')

  // An official result makes the race laps into track records.
  await page.goto(`/rounds/${round.id}`)
  await page.getByRole('button', { name: 'Aprobar como oficial' }).click()
  await expect(page.getByText('Oficial', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Récords' }).click()
  const raceBoard = page.getByRole('article', { name: /Récord de carrera: Highlands · Long · Acura/ })
  await expect(raceBoard).toContainText('3:09.296')
  await expect(raceBoard).toContainText('Driver 01')
})
