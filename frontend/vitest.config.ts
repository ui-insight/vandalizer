import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      // Denominator is the whole src/ tree, not just what a given test
      // happens to import. This makes the number honest (no more counting
      // only files pulled in transitively by tests) and, crucially,
      // monotonic: adding a test can only ever raise it, never lower it by
      // widening the denominator. See plan 009 for the incident this fixed.
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        '**/*.test.{ts,tsx}',
        'src/main.tsx',
        '**/*.d.ts',
      ],
      // Thresholds are single-sourced here (not duplicated in Makefile or
      // package.json). Set just below the honest whole-src measurement at
      // the time they were last raised — ratchet upward as more
      // components/hooks/api modules get tests. Do not lower these to make
      // a change pass; add tests instead.
      //
      // Measured whole-src baseline when this gate went live: ~6.4% lines /
      // 6.1% statements / 5.1% functions / 5.2% branches (previously
      // mis-measured as ~8%/8%/6%/6%, which failed CI on the honest number —
      // see the fix that corrected these to the real figures).
      thresholds: {
        statements: 6,
        branches: 5,
        functions: 5,
        lines: 6,
      },
    },
  },
})
