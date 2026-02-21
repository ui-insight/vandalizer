import { useEffect, useState } from 'react'
import { User, KeyRound, SlidersHorizontal, Save, Eye, EyeOff, Copy, Check, RefreshCw, Trash2, Globe } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { getUserConfig, updateUserConfig, getModels } from '../api/config'
import { generateApiToken, revokeApiToken, getApiTokenStatus } from '../api/auth'
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

  // API Token state
  const [hasToken, setHasToken] = useState(false)
  const [tokenCreatedAt, setTokenCreatedAt] = useState<string | null>(null)
  const [newToken, setNewToken] = useState<string | null>(null)
  const [tokenVisible, setTokenVisible] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [tokenLoading, setTokenLoading] = useState(true)
  const [tokenGenerating, setTokenGenerating] = useState(false)
  const [tokenRevoking, setTokenRevoking] = useState(false)

  useEffect(() => {
    getApiTokenStatus()
      .then(s => { setHasToken(s.has_token); setTokenCreatedAt(s.created_at) })
      .catch(() => {})
      .finally(() => setTokenLoading(false))
  }, [])

  const handleGenerateToken = async () => {
    if (hasToken && !confirm('This will replace your existing token. The Chrome extension will need to be reconfigured. Continue?')) return
    setTokenGenerating(true)
    try {
      const res = await generateApiToken()
      setNewToken(res.api_token)
      setHasToken(true)
      setTokenCreatedAt(res.created_at)
      setTokenVisible(true)
    } catch { /* ignore */ }
    finally { setTokenGenerating(false) }
  }

  const handleRevokeToken = async () => {
    if (!confirm('Are you sure you want to revoke this token? The Chrome extension will stop working.')) return
    setTokenRevoking(true)
    try {
      await revokeApiToken()
      setHasToken(false)
      setTokenCreatedAt(null)
      setNewToken(null)
    } catch { /* ignore */ }
    finally { setTokenRevoking(false) }
  }

  const handleCopyToken = () => {
    if (!newToken) return
    navigator.clipboard.writeText(newToken)
    setTokenCopied(true)
    setTimeout(() => setTokenCopied(false), 2000)
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
                      <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
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
          <div className="p-4 space-y-4">
            <p className="text-sm text-gray-600">
              Use an API token to access Vandalizer from the Chrome Extension or external integrations.
              Keep it secure — it provides full access to your account.
            </p>

            {tokenLoading ? (
              <p className="text-sm text-gray-400">Loading token status...</p>
            ) : hasToken ? (
              <>
                {/* Active token status */}
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-700">
                    <Check className="h-3 w-3" /> Active
                  </span>
                  {tokenCreatedAt && (
                    <span className="text-xs text-gray-400">
                      Created {new Date(tokenCreatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                  )}
                </div>

                {/* Show token if just generated */}
                {newToken && (
                  <div className="rounded-md border border-yellow-200 bg-yellow-50 p-3">
                    <p className="text-xs font-medium text-yellow-800 mb-2">
                      Copy your token now — it won't be shown again.
                    </p>
                    <div className="flex items-center gap-2">
                      <input
                        type={tokenVisible ? 'text' : 'password'}
                        value={newToken}
                        readOnly
                        className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-mono focus:outline-none"
                      />
                      <button
                        onClick={() => setTokenVisible(!tokenVisible)}
                        className="rounded-md border border-gray-300 p-2 text-gray-500 hover:bg-gray-50"
                        title={tokenVisible ? 'Hide token' : 'Show token'}
                      >
                        {tokenVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={handleCopyToken}
                        className="rounded-md border border-gray-300 p-2 text-gray-500 hover:bg-gray-50"
                        title="Copy to clipboard"
                      >
                        {tokenCopied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  <button
                    onClick={handleGenerateToken}
                    disabled={tokenGenerating}
                    className="flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    {tokenGenerating ? 'Regenerating...' : 'Regenerate'}
                  </button>
                  <button
                    onClick={handleRevokeToken}
                    disabled={tokenRevoking}
                    className="flex items-center gap-1.5 rounded-md border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {tokenRevoking ? 'Revoking...' : 'Revoke Token'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="rounded-md border border-blue-100 bg-blue-50 p-3">
                  <p className="text-sm text-blue-700">
                    You haven't generated an API token yet. Generate one to use with the Chrome Extension or external integrations.
                  </p>
                </div>
                <button
                  onClick={handleGenerateToken}
                  disabled={tokenGenerating}
                  className="flex items-center gap-1.5 rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
                >
                  <KeyRound className="h-4 w-4" />
                  {tokenGenerating ? 'Generating...' : 'Generate API Token'}
                </button>
              </>
            )}

            {/* Chrome Extension Setup */}
            {hasToken && (
              <div className="border-t border-gray-100 pt-4 mt-4">
                <div className="flex items-center gap-2 mb-2">
                  <Globe className="h-4 w-4 text-gray-400" />
                  <h4 className="text-sm font-medium text-gray-700">Chrome Extension Setup</h4>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Backend URL</label>
                    <input
                      type="text"
                      readOnly
                      value={window.location.origin}
                      className="w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-mono text-gray-600"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium uppercase text-gray-400 mb-1">User Token</label>
                    <input
                      type="text"
                      readOnly
                      value={newToken ? '(see above)' : '(token hidden)'}
                      className="w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-mono text-gray-600"
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  Enter these values in the Chrome Extension popup to connect.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </PageLayout>
  )
}
