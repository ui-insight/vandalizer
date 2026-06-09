import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { sentryVitePlugin } from '@sentry/vite-plugin'

// Only emit + upload source maps when an auth token is present. Without
// the token, the plugin would skip the upload but the maps would still
// land in `dist/` and get served by nginx — leaking original source.
const uploadSourceMaps = Boolean(process.env.SENTRY_AUTH_TOKEN)

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(uploadSourceMaps
      ? [
          sentryVitePlugin({
            org: process.env.SENTRY_ORG,
            project: process.env.SENTRY_PROJECT,
            authToken: process.env.SENTRY_AUTH_TOKEN,
            release: { name: process.env.VITE_SENTRY_RELEASE },
            sourcemaps: {
              filesToDeleteAfterUpload: ['./dist/**/*.map'],
            },
          }),
        ]
      : []),
  ],
  build: {
    sourcemap: uploadSourceMaps,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
    },
  },
})
