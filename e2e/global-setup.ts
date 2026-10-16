import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { E2E_ADMIN } from './fixtures'

const root = fileURLToPath(new URL('..', import.meta.url))

// The tests use their own Compose project, with their own database and ports.
// Your local app and its data stay as they are. global-teardown.ts deletes the test project.
export const E2E_PROJECT = 'paddock-e2e'
export const E2E_WEB_PORT = '8421'
const E2E_DB_PORT = '55433'

export function compose(args: string[], env: Record<string, string> = {}) {
  execFileSync('docker', ['compose', '--project-name', E2E_PROJECT, ...args], {
    cwd: root,
    stdio: 'inherit',
    // AI_DISABLED: the test app never makes a paid AI call, even with a key in .env.
    env: { ...process.env, WEB_PUBLISH_PORT: E2E_WEB_PORT, DB_PUBLISH_PORT: E2E_DB_PORT, AI_DISABLED: '1', ...env },
  })
}

export default function globalSetup() {
  if (process.env.E2E_BASE_URL) return // An external server is already running.
  compose(['down', '--volumes', '--remove-orphans']) // Remove data from a stopped earlier run.
  compose(['up', '--build', '--detach', '--wait'])
  compose(
    [
      'exec', '-T', '-e', 'FIRST_ADMIN_PASSWORD', 'web',
      'python', 'manage.py', 'create_first_admin', '--username', E2E_ADMIN.username,
    ],
    { FIRST_ADMIN_PASSWORD: E2E_ADMIN.password },
  )
}
