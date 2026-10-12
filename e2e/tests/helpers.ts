import { expect, type Page } from '@playwright/test'
import { E2E_ADMIN } from '../fixtures'

export async function signIn(page: Page) {
  await page.goto('/')
  await page.getByLabel('Usuario').fill(E2E_ADMIN.username)
  await page.getByLabel('Contraseña').fill(E2E_ADMIN.password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
}

/** Fill the fields of one form, found by its title, and send it. */
export async function submitForm(
  page: Page,
  title: string,
  fields: Record<string, string>,
  selects: Record<string, string> = {},
) {
  const form = page.getByRole('form', { name: title })
  // A select takes the text of its options into its name, so an exact match can miss it.
  const field = async (label: string) => {
    const exact = form.getByLabel(label, { exact: true })
    return (await exact.count()) > 0 ? exact : form.getByLabel(label)
  }
  for (const [label, value] of Object.entries(selects)) {
    await (await field(label)).selectOption({ label: value })
  }
  for (const [label, value] of Object.entries(fields)) {
    await (await field(label)).fill(value)
  }
  await form.locator('button[type=submit]').click()
}
