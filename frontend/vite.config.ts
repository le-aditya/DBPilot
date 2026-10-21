import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // The default forks pool fails to spawn on this Windows host ("spawn
    // UNKNOWN"), which silently dropped a test file from the run. Threads are
    // reliable here and keep every file in the suite.
    pool: 'threads',
  },
})
