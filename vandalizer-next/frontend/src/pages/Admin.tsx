import { useEffect, useState } from 'react'
import { Shield, Cpu, Users, BarChart3, Palette } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { getModels, getThemeConfig, updateThemeConfig } from '../api/config'
import type { ModelInfo } from '../types/workflow'
import type { ThemeConfig } from '../api/config'

function applyThemeToDOM(theme: ThemeConfig) {
  const root = document.documentElement
  root.style.setProperty('--highlight-color', theme.highlight_color)
  root.style.setProperty('--ui-radius', theme.ui_radius)
}

export default function Admin() {
  const { user } = useAuth()
  const [models, setModels] = useState<ModelInfo[]>([])
  const [modelsLoading, setModelsLoading] = useState(true)
  const [modelsError, setModelsError] = useState<string | null>(null)

  // Theme state
  const [theme, setTheme] = useState<ThemeConfig | null>(null)
  const [themeColor, setThemeColor] = useState('#eab308')
  const [themeRadius, setThemeRadius] = useState(12)
  const [themeSaving, setThemeSaving] = useState(false)
  const [themeSaved, setThemeSaved] = useState(false)

  useEffect(() => {
    setModelsLoading(true)
    setModelsError(null)
    getModels()
      .then(setModels)
      .catch((e) => setModelsError(e instanceof Error ? e.message : 'Failed to load models'))
      .finally(() => setModelsLoading(false))

    getThemeConfig()
      .then((t) => {
        setTheme(t)
        setThemeColor(t.highlight_color)
        setThemeRadius(parseInt(t.ui_radius) || 12)
      })
      .catch(() => {})
  }, [])

  const handleSaveTheme = async () => {
    setThemeSaving(true)
    setThemeSaved(false)
    try {
      const updated = await updateThemeConfig({
        highlight_color: themeColor,
        ui_radius: `${themeRadius}px`,
      })
      setTheme(updated)
      applyThemeToDOM(updated)
      setThemeSaved(true)
      setTimeout(() => setThemeSaved(false), 3000)
    } finally {
      setThemeSaving(false)
    }
  }

  if (!user?.is_admin) {
    return (
      <PageLayout>
        <div className="mx-auto max-w-3xl py-12 text-center">
          <Shield className="mx-auto h-10 w-10 text-gray-300 mb-4" />
          <h2 className="text-lg font-semibold text-gray-900">Access Denied</h2>
          <p className="mt-2 text-sm text-gray-500">
            You must be an administrator to view this page.
          </p>
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-gray-400" />
          <h2 className="text-xl font-semibold text-gray-900">Admin Panel</h2>
        </div>

        {/* Theme Configuration */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <Palette className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">UI Theme</h3>
          </div>
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-2 gap-6">
              {/* Highlight Color */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Highlight Color
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={themeColor}
                    onChange={(e) => setThemeColor(e.target.value)}
                    className="h-10 w-14 rounded border border-gray-300 cursor-pointer"
                  />
                  <input
                    type="text"
                    value={themeColor}
                    onChange={(e) => setThemeColor(e.target.value)}
                    className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-highlight"
                    placeholder="#eab308"
                  />
                </div>
              </div>

              {/* Corner Radius */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Corner Radius: {themeRadius}px
                </label>
                <input
                  type="range"
                  min={0}
                  max={24}
                  value={themeRadius}
                  onChange={(e) => setThemeRadius(Number(e.target.value))}
                  className="w-full mt-2"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>0px (sharp)</span>
                  <span>24px (round)</span>
                </div>
              </div>
            </div>

            {/* Preview */}
            <div className="flex items-center gap-4 pt-2">
              <div className="text-sm text-gray-500">Preview:</div>
              <div
                style={{
                  backgroundColor: themeColor,
                  borderRadius: `${themeRadius}px`,
                  padding: '8px 20px',
                  color: '#000',
                  fontWeight: 600,
                  fontSize: 13,
                }}
              >
                Sample Button
              </div>
              <div
                style={{
                  border: `2px solid ${themeColor}`,
                  borderRadius: `${themeRadius}px`,
                  padding: '8px 20px',
                  color: themeColor,
                  fontWeight: 600,
                  fontSize: 13,
                }}
              >
                Outline Button
              </div>
            </div>

            {/* Save */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleSaveTheme}
                disabled={themeSaving}
                className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {themeSaving ? 'Saving...' : 'Save Theme'}
              </button>
              {themeSaved && (
                <span className="text-sm text-green-600">Theme saved and applied!</span>
              )}
            </div>
          </div>
        </div>

        {/* System Config: Models */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <Cpu className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">Available Models</h3>
          </div>
          <div className="p-4">
            {modelsLoading ? (
              <div className="text-sm text-gray-500">Loading models...</div>
            ) : modelsError ? (
              <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{modelsError}</div>
            ) : models.length === 0 ? (
              <div className="text-sm text-gray-500">No models configured.</div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 text-left">
                    <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Name</th>
                    <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Tag</th>
                    <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">External</th>
                    <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Thinking</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {models.map((model) => (
                    <tr key={model.name}>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{model.name}</td>
                      <td className="px-4 py-3">
                        <span className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                          {model.tag}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {model.external ? (
                          <span className="text-yellow-600">Yes</span>
                        ) : (
                          <span className="text-gray-400">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {model.thinking ? (
                          <span className="text-blue-600">Yes</span>
                        ) : (
                          <span className="text-gray-400">No</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* User Info */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <Users className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">Current User</h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Name</span>
                <p className="font-medium text-gray-900">{user?.name || 'N/A'}</p>
              </div>
              <div>
                <span className="text-gray-500">Email</span>
                <p className="font-medium text-gray-900">{user?.email || 'N/A'}</p>
              </div>
              <div>
                <span className="text-gray-500">Role</span>
                <p className="font-medium text-gray-900">{user?.is_admin ? 'Administrator' : 'User'}</p>
              </div>
              <div>
                <span className="text-gray-500">User ID</span>
                <p className="font-mono text-xs text-gray-600 break-all">{user?.user_id || 'N/A'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* System Stats */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <BarChart3 className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">System Stats</h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="rounded-lg bg-blue-50 p-4 text-center">
                <div className="text-2xl font-bold text-blue-700">{models.length}</div>
                <div className="text-xs text-blue-600 mt-1">Available Models</div>
              </div>
              <div className="rounded-lg bg-green-50 p-4 text-center">
                <div className="text-2xl font-bold text-green-700">
                  {models.filter(m => m.external).length}
                </div>
                <div className="text-xs text-green-600 mt-1">External Models</div>
              </div>
              <div className="rounded-lg bg-purple-50 p-4 text-center">
                <div className="text-2xl font-bold text-purple-700">
                  {models.filter(m => m.thinking).length}
                </div>
                <div className="text-xs text-purple-600 mt-1">Thinking Models</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageLayout>
  )
}
