import { expect, type Locator, type Page } from '@playwright/test'
import { E2E_ADMIN } from '../fixtures'

export async function signIn(page: Page) {
  await page.goto('/')
  await page.getByLabel('Usuario').fill(E2E_ADMIN.username)
  await page.getByLabel('Contraseña').fill(E2E_ADMIN.password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  // The account menu shows only when the sign-in worked. A phone shows it in the header.
  await expect(page.getByRole('button', { name: `Menú de ${E2E_ADMIN.username}` })).toBeVisible()
}

/** Open the account menu and sign out. */
export async function signOut(page: Page) {
  await page.getByRole('button', { name: `Menú de ${E2E_ADMIN.username}` }).click()
  await page.getByRole('menuitem', { name: 'Cerrar sesión' }).click()
}

/** Fill the fields of one form, found by its title, and send it. */
export async function submitForm(
  page: Page,
  title: string,
  fields: Record<string, string>,
  selects: Record<string, string> = {},
) {
  const form = page.getByRole('form', { name: title, exact: true })
  await form.waitFor() // count() does not wait, so wait for the form first.
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

/** A link of the side menu. A count can follow the name, for example "Cuentas, 1 pendiente". */
export function navLink(page: Page, name: string): Locator {
  return page
    .getByRole('navigation', { name: 'Navegación principal' })
    .getByRole('link', { name: new RegExp(`^${name}( ?,|$)`) })
}

/** Open an admin form of a season page section in its dialog. A section with one form has a button
 * with the form name. A section with more forms has an "Administrar" menu. */
export async function openAdminForm(page: Page, sectionId: string, name: string) {
  const section = page.locator(`#${sectionId}`)
  const button = section.getByRole('button', { name, exact: true })
  if ((await button.count()) === 0) await section.getByRole('button', { name: 'Administrar', exact: true }).click()
  await button.click()
}

