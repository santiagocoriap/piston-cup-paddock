import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Django serves the production build under /static/.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/' : '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/django-admin': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
}))
