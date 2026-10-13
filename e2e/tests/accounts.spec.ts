import { expect, test } from '@playwright/test'
import { navLink, signIn, submitForm } from './helpers'

test('an admin invites a driver, and the driver sets a password and signs in', async ({
  page,
  browser,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'One run is enough. The flow writes data.')
  const username = `driver_${Date.now().toString(36)}`
  await signIn(page)
  await page.getByRole('button', { name: 'Modo admin' }).click()
  await navLink(page, 'Cuentas').click()
  await page.getByRole('button', { name: 'Nueva cuenta' }).click()
  await submitForm(page, 'Nueva cuenta', { Usuario: username })

  const box = page.getByRole('region', { name: `Link para ${username}` })
  const link = await box.getByRole('textbox').inputValue()
  expect(link).toContain('/invite#')

  // The driver opens the link in another browser, with no session.
  const driverContext = await browser.newContext()
  const driver = await driverContext.newPage()
  await driver.goto(link)
  await expect(driver.getByText(`Hola, ${username}.`, { exact: false })).toBeVisible()
  await driver.getByLabel('Contraseña', { exact: true }).fill('driver-pass-5521')
  await driver.getByLabel('Repetí la contraseña').fill('driver-pass-5521')
  await driver.getByRole('button', { name: 'Guardar y entrar' }).click()
  await expect(driver.getByRole('heading', { level: 1, name: `Hola, ${username}` })).toBeVisible()
  expect(new URL(driver.url()).hash).toBe('')

  // The same link does not work a second time.
  const second = await browser.newContext()
  const again = await second.newPage()
  await again.goto(link)
  await expect(again.getByRole('alert')).toContainText('ya se usó o venció')
  await driverContext.close()
  await second.close()
})
