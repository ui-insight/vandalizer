import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initSentry } from './lib/sentry'
// Self-hosted Public Sans (variable, wght 100-900). Bundled by Vite so the SPA
// has no third-party font request at runtime — offline installs must not block
// on fonts.googleapis.com.
import '@fontsource-variable/public-sans'
import './index.css'
import App from './App.tsx'

initSentry()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
