import { useEffect, useState } from 'react'
import { User, KeyRound, SlidersHorizontal, Save } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { getUserConfig, updateUserConfig, getModels } from '../api/config'
import type { ModelInfo } from '../types/workflow'

export default function Account() {
  const { user } = useAuth()

  // Model preferences
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [topP, setTopP] = useState(1)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [configLoading, setConfigLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getUserConfig(), getModels()])
      .then(([config, modelList]) => {
        setModel(config.model)
        setTemperature(config.temperature)
        setTopP(config.top_p)
        setModels(modelList)
      })
      .catch(() => {})
      .finally(() => setConfigLoading(false))
  }, [])

  const handleSavePreferences = async () => {
    setSaving(true)
    setSaveMessage(null)
    try {
      await updateUserConfig({ model, temperature, top_p: topP })
      setSaveMessage('Preferences saved')
      setTimeout(() => setSaveMessage(null), 3000)
    } catch {
      setSaveMessage('Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        <h2 className="text-xl font-semibold text-gray-900">My Account</h2>

        {/* Account Information */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <User className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">Account Information</h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-2 gap-x-8 gap-y-4">
              <div>
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">User ID</label>
                <p className="text-sm font-mono text-gray-900">{user?.user_id || '—'}</p>
              </div>
              <div>
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Display Name</label>
                <p className="text-sm text-gray-900">{user?.name || 'Not set'}</p>
              </div>
              <div>
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Email</label>
                <p className="text-sm text-gray-900">{user?.email || 'Not set'}</p>
              </div>
              <div>
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Role</label>
                <p className="text-sm text-gray-900">{user?.is_admin ? 'Administrator' : 'Member'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Model Preferences */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <SlidersHorizontal className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">Model Preferences</h3>
          </div>
          <div className="p-4">
            {configLoading ? (
              <p className="text-sm text-gray-500">Loading...</p>
            ) : (
              <div className="space-y-4">
                {/* Default model */}
                <div>
                  <label className="block text-xs font-medium uppercase text-gray-400 mb-1">
                    Default Model
                  </label>
                  <select
                    value={model}
                    onChange={e => setModel(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                  >
                    {models.map(m => (
                      <option key={m.name} value={m.name}>{m.name}</option>
                    ))}
                  </select>
                </div>

                {/* Temperature */}
                <div>
                  <label className="block text-xs font-medium uppercase text-gray-400 mb-1">
                    Temperature
                    <span className="ml-2 normal-case font-normal text-gray-400">{temperature.toFixed(2)}</span>
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={2}
                    step={0.05}
                    value={temperature}
                    onChange={e => setTemperature(parseFloat(e.target.value))}
                    className="w-full accent-[var(--highlight-color)]"
                  />
                  <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
                    <span>Precise (0)</span>
                    <span>Creative (2)</span>
                  </div>
                </div>

                {/* Top-P */}
                <div>
                  <label className="block text-xs font-medium uppercase text-gray-400 mb-1">
                    Top P
                    <span className="ml-2 normal-case font-normal text-gray-400">{topP.toFixed(2)}</span>
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={topP}
                    onChange={e => setTopP(parseFloat(e.target.value))}
                    className="w-full accent-[var(--highlight-color)]"
                  />
                  <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
                    <span>Focused (0)</span>
                    <span>Diverse (1)</span>
                  </div>
                </div>

                {/* Save */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSavePreferences}
                    disabled={saving}
                    className="flex items-center gap-1.5 rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
                  >
                    <Save className="h-4 w-4" />
                    {saving ? 'Saving...' : 'Save Preferences'}
                  </button>
                  {saveMessage && (
                    <span className="text-sm text-green-600">{saveMessage}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* API Token */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <KeyRound className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">API Token</h3>
          </div>
          <div className="p-4">
            <p className="text-sm text-gray-600 mb-3">
              Use an API token to access Vandalizer from the Chrome Extension or external integrations.
              Keep it secure — it provides full access to your account.
            </p>
            <p className="text-xs text-gray-400">
              API token management is available in the main application settings.
            </p>
          </div>
        </div>
      </div>
    </PageLayout>
  )
}
