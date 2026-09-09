import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'
import prettier from 'eslint-config-prettier'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      prettier,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Code-Review 2026-09-09, Etappe 0: Diese 21 Befunde sind inhaltlich, nicht
      // formatierend — sie aendern Verhalten oder verlangen ein Refactoring und
      // gehoeren damit in Etappe 4, nicht in die Werkzeug-Etappe. Bis dahin stehen
      // sie als Warnung da, und `npm run lint` deckelt die Zahl per --max-warnings.
      // Sie darf nur sinken. Beim Beheben: Eintrag hier und die Zahl in package.json
      // gemeinsam entfernen.
      'react-hooks/static-components': 'warn', // 8x — Komponenten im Render definiert
      'react-refresh/only-export-components': 'warn', // 5x — reviewShared.tsx mischt
      '@typescript-eslint/no-explicit-any': 'warn', // 3x — Typschulden
      'react-hooks/exhaustive-deps': 'warn', // 3x — Gefahr veralteter Closures
      'react-hooks/set-state-in-effect': 'warn', // 2x — kaskadierende Renders
    },
  },
])
