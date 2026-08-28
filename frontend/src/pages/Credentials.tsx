import { useEffect, useMemo, useState } from 'react'
import { KeyRound, Plus, Pencil, Trash2, RefreshCw , Plug } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useConfirm } from '../components/shared/useConfirm'
import {
  createCredential,
  deleteCredential,
  invalidateCredentialCache,
  testCredential,
  testCredentialDraft,
  listCredentials,
  updateCredential,
} from '../api/credentials'
import { CredentialTestPanel } from '../components/credentials/CredentialTestPanel'
import { useToast } from '../contexts/ToastContext'
import type { Credential, CredentialType } from '../types/credential'

const TYPE_LABELS: Record<CredentialType, string> = {
  static_header: 'Static header',
  oauth_client_credentials: 'OAuth (client_credentials JWT)',
}

interface FormState {
  name: string
  type: CredentialType
  description: string
  // static_header
  header_name: string
  header_value: string
  // oauth_client_credentials
  client_id: string
  token_endpoint: string
  private_key: string
  scope: string
  audience: string
  algorithm: string
  test_url: string
}

const EMPTY_FORM: FormState = {
  name: '',
  type: 'static_header',
  description: '',
  header_name: '',
  header_value: '',
  client_id: '',
  token_endpoint: '',
  private_key: '',
  scope: '',
  audience: '',
  algorithm: 'RS256',
  test_url: '',
}

function buildPayload(form: FormState): Record<string, string> {
  if (form.type === 'static_header') {
    const p: Record<string, string> = { header_name: form.header_name, header_value: form.header_value }
    if (form.test_url) p.test_url = form.test_url
    return p
  }
  const payload: Record<string, string> = {
    client_id: form.client_id,
    token_endpoint: form.token_endpoint,
    private_key: form.private_key,
  }
  if (form.scope) payload.scope = form.scope
  if (form.audience) payload.audience = form.audience
  if (form.algorithm && form.algorithm !== 'RS256') payload.algorithm = form.algorithm
  if (form.test_url) payload.test_url = form.test_url
  return payload
}

// On edit the secret is never prefilled (the API never returns it), so we only
// send a secret field when the user typed a new value — blank means "keep the
// current one". The backend merges these over the stored payload.
function buildUpdatePayload(form: FormState): Record<string, string> {
  if (form.type === 'static_header') {
    const p: Record<string, string> = { header_name: form.header_name, test_url: form.test_url }
    if (form.header_value) p.header_value = form.header_value
    return p
  }
  const p: Record<string, string> = {
    client_id: form.client_id,
    token_endpoint: form.token_endpoint,
    test_url: form.test_url,
  }
  if (form.scope) p.scope = form.scope
  if (form.audience) p.audience = form.audience
  if (form.algorithm && form.algorithm !== 'RS256') p.algorithm = form.algorithm
  if (form.private_key) p.private_key = form.private_key
  return p
}

// True if any non-secret payload field differs from the stored credential, so a
// rename-only edit doesn't needlessly resend the payload (which would drop the
// cached bearer token).
function nonSecretChanged(form: FormState, original: Credential): boolean {
  const p = original.payload || {}
  if (form.test_url !== (p.test_url ?? '')) return true
  if (form.type === 'static_header') {
    return form.header_name !== (p.header_name ?? '')
  }
  return (
    form.client_id !== (p.client_id ?? '') ||
    form.token_endpoint !== (p.token_endpoint ?? '') ||
    form.scope !== (p.scope ?? '') ||
    form.audience !== (p.audience ?? '') ||
    (form.algorithm || 'RS256') !== (p.algorithm || 'RS256')
  )
}

export default function Credentials() {
  const confirm = useConfirm()
  const { toast } = useToast()
  const [creds, setCreds] = useState<Credential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  const loadCreds = async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await listCredentials()
      setCreds(list)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load credentials')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCreds()
  }, [])

  const closeForm = () => {
    setShowForm(false)
    setForm(EMPTY_FORM)
    setEditingId(null)
  }

  const startCreate = () => {
    if (showForm && !editingId) {
      closeForm()
      return
    }
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  const startEdit = (cred: Credential) => {
    const p = cred.payload || {}
    setForm({
      name: cred.name,
      type: cred.type,
      description: cred.description ?? '',
      header_name: p.header_name ?? '',
      header_value: '', // secret never returned — leave blank to keep
      client_id: p.client_id ?? '',
      token_endpoint: p.token_endpoint ?? '',
      private_key: '', // secret never returned — leave blank to keep
      scope: p.scope ?? '',
      audience: p.audience ?? '',
      algorithm: p.algorithm || 'RS256',
      test_url: p.test_url ?? '',
    })
    setEditingId(cred.id)
    setShowForm(true)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      if (editingId) {
        const secretEntered = form.type === 'static_header' ? !!form.header_value : !!form.private_key
        const data: { name?: string; description?: string; payload?: Record<string, string>; type?: CredentialType } = {
          name: form.name,
          description: form.description,
        }
        if (typeChanged) {
          // A type change is a fresh credential under the same id: send the
          // new type and its complete payload.
          data.type = form.type
          data.payload = buildPayload(form)
        } else if (original && (secretEntered || nonSecretChanged(form, original))) {
          // Only resend the payload when something in it actually changed, so
          // a pure rename doesn't drop the cached OAuth token.
          data.payload = buildUpdatePayload(form)
        }
        const updated = await updateCredential(editingId, data)
        if (typeChanged && updated.steps_updated) {
          toast(`Credential type changed; ${updated.steps_updated} API step${updated.steps_updated === 1 ? '' : 's'} updated to match`, 'info')
        }
      } else {
        await createCredential({
          name: form.name,
          type: form.type,
          description: form.description || undefined,
          payload: buildPayload(form),
        })
      }
      closeForm()
      await loadCreds()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save credential')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    const cred = creds.find(c => c.id === id)
    const ok = await confirm({
      title: 'Delete credential?',
      message: (
        <>
          Are you sure you want to delete <strong>{cred?.name || 'this credential'}</strong>? Workflows referencing it will fail.
        </>
      ),
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteCredential(id)
      await loadCreds()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  const [testingId, setTestingId] = useState<string | null>(null)
  const [testUrls, setTestUrls] = useState<Record<string, string>>({})

  const handleInvalidate = async (id: string) => {
    try {
      await invalidateCredentialCache(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to invalidate cache')
    }
  }

  // Editing a credential into another type: the stored secrets belong to the
  // old type, so the new type's fields — secret included — are all required,
  // exactly as when creating.
  const original = editingId ? creds.find(c => c.id === editingId) : undefined
  const typeChanged = !!original && original.type !== form.type
  const formValid = useMemo(() => {
    if (!form.name.trim()) return false
    // On edit, the secret may be left blank to keep the stored one — unless
    // the type changed, in which case there is nothing stored to keep.
    const editing = editingId !== null && !typeChanged
    if (form.type === 'static_header') {
      return !!form.header_name && (editing || !!form.header_value)
    }
    return !!form.client_id && !!form.token_endpoint && (editing || !!form.private_key)
  }, [form, editingId, typeChanged])

  return (
    <PageLayout>
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-900">Credentials</h1>
          <button
            onClick={startCreate}
            className="flex items-center gap-1.5 rounded-md bg-highlight px-3 py-1.5 text-sm font-bold text-highlight-text hover:brightness-90"
          >
            <Plus className="h-4 w-4" />
            New credential
          </button>
        </div>

        <p className="text-sm text-gray-600">
          Credentials are referenced by ID from API Node steps in workflows. Secret values
          are encrypted at rest and never returned by the API after creation.
        </p>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {showForm && (
          <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
            <h3 className="font-medium text-gray-900">
              {editingId ? 'Edit credential' : 'New credential'}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="cred-name" className="block text-xs font-medium uppercase text-gray-500 mb-1">Name</label>
                <input
                  id="cred-name"
                  type="text"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                  placeholder="e.g. Lakehouse OAuth"
                />
              </div>
              <div>
                <label htmlFor="cred-type" className="block text-xs font-medium uppercase text-gray-500 mb-1">Type</label>
                <select
                  id="cred-type"
                  value={form.type}
                  onChange={e => setForm({ ...form, type: e.target.value as CredentialType })}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                >
                  <option value="static_header">{TYPE_LABELS.static_header}</option>
                  <option value="oauth_client_credentials">
                    {TYPE_LABELS.oauth_client_credentials}
                  </option>
                </select>
                {typeChanged && (
                  <p role="note" className="mt-1 text-xs text-amber-700">
                    Changing the type replaces the stored secrets — enter the {TYPE_LABELS[form.type]} details in full.
                    API steps that use this credential will be switched to the new type when you save.
                  </p>
                )}
              </div>
            </div>

            <div>
              <label htmlFor="cred-description" className="block text-xs font-medium uppercase text-gray-500 mb-1">Description</label>
              <input
                id="cred-description"
                type="text"
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                placeholder="Optional"
              />
            </div>

            {form.type === 'static_header' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="cred-header-name" className="block text-xs font-medium uppercase text-gray-500 mb-1">Header name</label>
                  <input
                    id="cred-header-name"
                    type="text"
                    value={form.header_name}
                    onChange={e => setForm({ ...form, header_name: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                    placeholder="X-Api-Key"
                  />
                </div>
                <div>
                  <label htmlFor="cred-header-value" className="block text-xs font-medium uppercase text-gray-500 mb-1">Header value</label>
                  <input
                    id="cred-header-value"
                    type="password"
                    autoComplete="new-password"
                    data-1p-ignore
                    data-lpignore="true"
                    data-bwignore
                    name="vandalizer-credential-header-value-page"
                    value={form.header_value}
                    onChange={e => setForm({ ...form, header_value: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                    placeholder={editingId && !typeChanged ? 'Leave blank to keep current' : 'secret'}
                  />
                </div>
              </div>
            )}

            {form.type === 'oauth_client_credentials' && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="cred-client-id" className="block text-xs font-medium uppercase text-gray-500 mb-1">Client ID</label>
                    <input
                      id="cred-client-id"
                      type="text"
                      value={form.client_id}
                      onChange={e => setForm({ ...form, client_id: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                    />
                  </div>
                  <div>
                    <label htmlFor="cred-token-endpoint" className="block text-xs font-medium uppercase text-gray-500 mb-1">Token endpoint</label>
                    <input
                      id="cred-token-endpoint"
                      type="url"
                      value={form.token_endpoint}
                      onChange={e => setForm({ ...form, token_endpoint: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                      placeholder="https://issuer/oauth/token"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label htmlFor="cred-scope" className="block text-xs font-medium uppercase text-gray-500 mb-1">Scope</label>
                    <input
                      id="cred-scope"
                      type="text"
                      value={form.scope}
                      onChange={e => setForm({ ...form, scope: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                      placeholder="read write"
                    />
                  </div>
                  <div>
                    <label htmlFor="cred-audience" className="block text-xs font-medium uppercase text-gray-500 mb-1">Audience</label>
                    <input
                      id="cred-audience"
                      type="text"
                      value={form.audience}
                      onChange={e => setForm({ ...form, audience: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                      placeholder="(default: token endpoint)"
                    />
                  </div>
                  <div>
                    <label htmlFor="cred-algorithm" className="block text-xs font-medium uppercase text-gray-500 mb-1">Algorithm</label>
                    <select
                      id="cred-algorithm"
                      value={form.algorithm}
                      onChange={e => setForm({ ...form, algorithm: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                    >
                      <option value="RS256">RS256</option>
                      <option value="RS384">RS384</option>
                      <option value="RS512">RS512</option>
                      <option value="ES256">ES256</option>
                      <option value="ES384">ES384</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label htmlFor="cred-private-key" className="block text-xs font-medium uppercase text-gray-500 mb-1">Private key (PEM)</label>
                  <textarea
                    id="cred-private-key"
                    value={form.private_key}
                    onChange={e => setForm({ ...form, private_key: e.target.value })}
                    rows={8}
                    className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-xs font-mono focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                    placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
                  />
                  {editingId && (
                    <p className="mt-1 text-xs text-gray-500">
                      Paste a new key to rotate it. Leave blank to keep the current key.
                    </p>
                  )}
                </div>
              </>
            )}

            <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
              <div className="mb-2 text-xs font-semibold text-gray-700">Test this credential</div>
              <CredentialTestPanel
                testUrl={form.test_url}
                onTestUrlChange={url => setForm(f => ({ ...f, test_url: url }))}
                disabled={!formValid}
                run={testUrl => editingId && !typeChanged
                  ? testCredential(editingId, { payload: buildUpdatePayload(form), test_url: testUrl || undefined })
                  : testCredentialDraft({ type: form.type, payload: buildPayload(form), test_url: testUrl || undefined })}
              />
            </div>

            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={handleSave}
                disabled={!formValid || saving}
                className="rounded-md bg-highlight px-4 py-1.5 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
              >
                {saving ? 'Saving...' : editingId ? 'Save changes' : 'Save credential'}
              </button>
              <button
                onClick={closeForm}
                className="rounded-md border border-gray-300 bg-white px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <KeyRound className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">Stored credentials</h3>
          </div>

          {loading ? (
            <div className="p-4 text-sm text-gray-500">Loading...</div>
          ) : creds.length === 0 ? (
            <div className="p-4 text-sm text-gray-500">No credentials yet.</div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {creds.map(cred => (
                <li key={cred.id} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">{cred.name}</span>
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-mono text-gray-600">
                        {TYPE_LABELS[cred.type]}
                      </span>
                      {cred.team_id && (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">team</span>
                      )}
                    </div>
                    {cred.description && (
                      <div className="mt-1 text-xs text-gray-500 truncate">{cred.description}</div>
                    )}
                    <div className="mt-1 text-xs font-mono text-gray-500">{cred.id}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setTestingId(t => (t === cred.id ? null : cred.id))}
                      title="Test this credential"
                      aria-pressed={testingId === cred.id}
                      className="flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                    >
                      <Plug className="h-3 w-3" />
                      Test
                    </button>
                    {cred.type === 'oauth_client_credentials' && (
                      <button
                        onClick={() => handleInvalidate(cred.id)}
                        title="Drop cached bearer token"
                        className="flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                      >
                        <RefreshCw className="h-3 w-3" />
                        Invalidate
                      </button>
                    )}
                    {cred.can_manage && (
                      <button
                        onClick={() => startEdit(cred)}
                        title="Edit credential"
                        className="flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                      >
                        <Pencil className="h-3 w-3" />
                        Edit
                      </button>
                    )}
                    {cred.can_manage && (
                      <button
                        onClick={() => handleDelete(cred.id)}
                        title="Delete credential"
                        className="flex items-center gap-1 rounded-md border border-red-200 bg-white px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                      >
                        <Trash2 className="h-3 w-3" />
                        Delete
                      </button>
                    )}
                  </div>
                </div>
                {testingId === cred.id && (
                  <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3">
                    <CredentialTestPanel
                      testUrl={testUrls[cred.id] ?? cred.payload?.test_url ?? ''}
                      onTestUrlChange={url => setTestUrls(u => ({ ...u, [cred.id]: url }))}
                      run={testUrl => testCredential(cred.id, { test_url: testUrl || undefined })}
                    />
                  </div>
                )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </PageLayout>
  )
}
