import { useEffect, useState } from 'react'
import { User, KeyRound, Save, Eye, EyeOff, Copy, Check, RefreshCw, Trash2, Code } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { generateApiToken, revokeApiToken, getApiTokenStatus, updateProfile } from '../api/auth'

export default function Account() {
  const { user, refreshUser } = useAuth()

  // Editable profile state
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileMessage, setProfileMessage] = useState<string | null>(null)

  useEffect(() => {
    if (user) {
      setName(user.name || '')
      setEmail(user.email || '')
    }
  }, [user])

  const handleSaveProfile = async () => {
    setProfileSaving(true)
    setProfileMessage(null)
    try {
      await updateProfile({ name, email })
      await refreshUser()
      setProfileMessage('Profile saved')
      setTimeout(() => setProfileMessage(null), 3000)
    } catch {
      setProfileMessage('Failed to save')
    } finally {
      setProfileSaving(false)
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
  const [tokenError, setTokenError] = useState<string | null>(null)

  useEffect(() => {
    getApiTokenStatus()
      .then(s => { setHasToken(s.has_token); setTokenCreatedAt(s.created_at) })
      .catch(err => { 
        const errorMessage = err instanceof Error ? err.message : 'Failed to load token status'
        setTokenError(`Failed to load API token status: ${errorMessage}`)
        console.error('Error loading API token status:', err)
      })
      .finally(() => setTokenLoading(false))
  }, [])

  const handleGenerateToken = async () => {
    if (hasToken && !confirm('This will replace your existing token. Continue?')) return
    setTokenGenerating(true)
    setTokenError(null)
    try {
      const res = await generateApiToken()
      setNewToken(res.api_token)
      setHasToken(true)
      setTokenCreatedAt(res.created_at)
      setTokenVisible(true)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to generate token'
      setTokenError(`Failed to generate API token: ${errorMessage}`)
      console.error('Error generating API token:', err)
    } finally { setTokenGenerating(false) }
  }

  const handleRevokeToken = async () => {
    if (!confirm('Are you sure you want to revoke this token?')) return
    setTokenRevoking(true)
    setTokenError(null)
    try {
      await revokeApiToken()
      setHasToken(false)
      setTokenCreatedAt(null)
      setNewToken(null)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to revoke token'
      setTokenError(`Failed to revoke API token: ${errorMessage}`)
      console.error('Error revoking API token:', err)
    } finally { setTokenRevoking(false) }
  }

  const handleCopyToken = () => {
    if (!newToken) return
    navigator.clipboard.writeText(newToken)
    setTokenCopied(true)
    setTimeout(() => setTokenCopied(false), 2000)
  }

  // API code sample tab
  const [apiTab, setApiTab] = useState<'python' | 'bash'>('python')
  const baseUrl = window.location.origin

  const pythonSample = `import requests

BASE_URL = "${baseUrl}"
API_TOKEN = "YOUR_API_TOKEN"
HEADERS = {"x-api-key": API_TOKEN}

# --- Run an extraction ---
with open("document.pdf", "rb") as f:
    resp = requests.post(
        f"{BASE_URL}/api/extractions/run-integrated",
        headers=HEADERS,
        data={"search_set_uuid": "YOUR_SEARCH_SET_UUID"},
        files={"files": ("document.pdf", f, "application/pdf")},
    )
activity_id = resp.json()["activity_id"]
print("Queued:", activity_id)

# --- Check status ---
status = requests.get(
    f"{BASE_URL}/api/extractions/status/{activity_id}",
    headers=HEADERS,
).json()
print("Status:", status["status"])

# --- Run a workflow ---
with open("document.pdf", "rb") as f:
    resp = requests.post(
        f"{BASE_URL}/api/workflows/run-integrated",
        headers=HEADERS,
        data={"workflow_id": "YOUR_WORKFLOW_ID"},
        files={"files": ("document.pdf", f, "application/pdf")},
    )
print("Queued:", resp.json()["activity_id"])`

  const bashSample = `BASE_URL="${baseUrl}"
API_TOKEN="YOUR_API_TOKEN"

# --- Run an extraction ---
curl -X POST "$BASE_URL/api/extractions/run-integrated" \\
  -H "x-api-key: $API_TOKEN" \\
  -F "search_set_uuid=YOUR_SEARCH_SET_UUID" \\
  -F "files=@document.pdf"

# --- Check status ---
curl "$BASE_URL/api/extractions/status/ACTIVITY_ID" \\
  -H "x-api-key: $API_TOKEN"

# --- Run a workflow ---
curl -X POST "$BASE_URL/api/workflows/run-integrated" \\
  -H "x-api-key: $API_TOKEN" \\
  -F "workflow_id=YOUR_WORKFLOW_ID" \\
  -F "files=@document.pdf"`

  return (
    <PageLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        <h2 className="text-xl font-semibold text-gray-900">My Account</h2>

        {/* Account Information — editable */}
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
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Role</label>
                <p className="text-sm text-gray-900">{user?.is_admin ? 'Administrator' : 'Member'}</p>
              </div>
              <div>
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Display Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                  placeholder="Your name"
                />
              </div>
              <div>
                <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                  placeholder="you@example.com"
                />
              </div>
            </div>
            <div className="flex items-center gap-3 mt-4">
              <button
                onClick={handleSaveProfile}
                disabled={profileSaving}
                className="flex items-center gap-1.5 rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
              >
                <Save className="h-4 w-4" />
                {profileSaving ? 'Saving...' : 'Save Profile'}
              </button>
              {profileMessage && (
                <span className={`text-sm ${profileMessage === 'Profile saved' ? 'text-green-600' : 'text-red-600'}`}>
                  {profileMessage}
                </span>
              )}
            </div>
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
              Use an API token to access Vandalizer from external integrations.
              Keep it secure — it provides full access to your account.
            </p>

            {tokenError && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3">
                <p className="text-sm text-red-700">{tokenError}</p>
              </div>
            )}

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
                    You haven't generated an API token yet. Generate one to use with external integrations.
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

          </div>
        </div>

        {/* API Integration */}
        {hasToken && (
          <div className="rounded-lg border border-gray-200 bg-white">
            <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
              <Code className="h-4 w-4 text-gray-400" />
              <h3 className="font-medium text-gray-900">API Integration</h3>
            </div>
            <div className="p-4 space-y-4">
              <p className="text-sm text-gray-600">
                Use these code samples to integrate Vandalizer into your applications.
                Replace <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">YOUR_API_TOKEN</code> with your token above.
                See <a href="/api/docs" className="text-blue-600 hover:underline" target="_blank">/api/docs</a> for the full Swagger reference.
              </p>

              {/* Tabs */}
              <div className="flex gap-1 border-b border-gray-200">
                {(['python', 'bash'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setApiTab(tab)}
                    className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      apiTab === tab
                        ? 'border-highlight text-gray-900'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {tab === 'python' ? 'Python' : 'Bash / cURL'}
                  </button>
                ))}
              </div>

              {/* Code block */}
              <pre className="overflow-x-auto rounded-md bg-gray-900 p-4 text-xs text-gray-100 leading-relaxed">
                <code>{apiTab === 'python' ? pythonSample : bashSample}</code>
              </pre>
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  )
}
