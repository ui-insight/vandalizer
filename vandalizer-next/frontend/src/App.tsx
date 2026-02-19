import { useEffect } from 'react'
import { RouterProvider } from '@tanstack/react-router'
import { AuthProvider } from './contexts/AuthContext'
import { TeamProvider } from './contexts/TeamContext'
import { router } from './router'
import { getThemeConfig } from './api/config'

function useThemeLoader() {
  useEffect(() => {
    getThemeConfig()
      .then((theme) => {
        const root = document.documentElement
        root.style.setProperty('--highlight-color', theme.highlight_color)
        root.style.setProperty('--ui-radius', theme.ui_radius)
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
        <RouterProvider router={router} />
      </TeamProvider>
    </AuthProvider>
  )
}
