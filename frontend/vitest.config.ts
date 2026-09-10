import path from 'path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'text'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/main.tsx', 'src/vite-env.d.ts'],
      // Ratsche, keine Zielvorgabe: Der Wert am 2026-09-10 war 77,49 %. Die Grenze
      // darf nur steigen. Sie zwingt niemanden, Tests zu schreiben — sie verhindert,
      // dass die Abdeckung unbemerkt sinkt. Wer sie senkt, tut das in einem Commit,
      // und das ist sichtbar.
      thresholds: {
        lines: 77,
        statements: 77,
        branches: 79,
        functions: 62,
      },
    },
  },
})
