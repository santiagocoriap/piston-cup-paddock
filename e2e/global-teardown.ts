import { compose } from './global-setup'

/** Delete the test containers and the test database after each run. */
export default function globalTeardown() {
  if (process.env.E2E_BASE_URL) return
  if (process.env.E2E_KEEP_STACK === 'true') return // Keep the stack to look at a failure.
  compose(['down', '--volumes', '--remove-orphans'])
}
