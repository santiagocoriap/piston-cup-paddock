import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { E2E_ADMIN } from './fixtures'

const root = fileURLToPath(new URL('..', import.meta.url))

function compose(args: string[], env: Record<string, string> = {}) {
  execFileSync('docker', ['compose', ...args], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, ...env },
  })
}

export default function globalSetup() {
  if (process.env.E2E_BASE_URL) return // An external server is already running.
  compose(['up', '--build', '--detach', '--wait'])
  compose(
    [
      'exec', '-T', '-e', 'FIRST_ADMIN_PASSWORD', 'web',
      'python', 'manage.py', 'create_first_admin', '--username', E2E_ADMIN.username, '--if-missing',
    ],
    { FIRST_ADMIN_PASSWORD: E2E_ADMIN.password },
  )
}
