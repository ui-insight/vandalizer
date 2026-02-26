import { useEffect } from 'react'
import { RouterProvider } from '@tanstack/react-router'
import { AuthProvider } from './contexts/AuthContext'
import { TeamProvider } from './contexts/TeamContext'
import { ToastProvider } from './contexts/ToastContext'
import { router } from './router'
import { getThemeConfig } from './api/config'
import { getContrastTextColor, getComplementaryColor } from './utils/color'

function useThemeLoader() {
  useEffect(() => {
    getThemeConfig()
      .then((theme) => {
        const root = document.documentElement
        root.style.setProperty('--highlight-color', theme.highlight_color)
        root.style.setProperty('--ui-radius', theme.ui_radius)
        root.style.setProperty('--highlight-text-color', getContrastTextColor(theme.highlight_color))
        root.style.setProperty('--highlight-complement', getComplementaryColor(theme.highlight_color))
      })
      .catch(() => {
        // Use CSS defaults if theme fetch fails (e.g. not logged in)
      })
  }, [])
}

export default function App() {
  useThemeLoader()

  return (
    <AuthProvider>
      <TeamProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </TeamProvider>
    </AuthProvider>
  )
}
