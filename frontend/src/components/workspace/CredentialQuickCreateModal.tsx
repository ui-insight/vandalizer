import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { FocusTrap } from 'focus-trap-react'
import { X } from 'lucide-react'
import { createCredential } from '../../api/credentials'
import type { Credential, CredentialType } from '../../types/credential'

interface Props {
  open: boolean
  initialType: CredentialType
  onClose: () => void
  onCreated: (cred: Credential) => void
}

interface FormState {
  name: string
  type: CredentialType
  description: string
  header_name: string
  header_value: string
  client_id: string
  token_endpoint: string
  private_key: string
  scope: string
  audience: string
  algorithm: string
}

const emptyForm = (type: CredentialType): FormState => ({
  name: '',
  type,
  description: '',
  header_name: '',
  header_value: '',
  client_id: '',
  token_endpoint: '',
  private_key: '',
  scope: '',
  audience: '',
  algorithm: 'RS256',
})

function buildPayload(form: FormState): Record<string, string> {
  if (form.type === 'static_header') {
    return { header_name: form.header_name, header_value: form.header_value }
  }
  const payload: Record<string, string> = {
    client_id: form.client_id,
    token_endpoint: form.token_endpoint,
    private_key: form.private_key,
  }
  if (form.scope) payload.scope = form.scope
  if (form.audience) payload.audience = form.audience
  if (form.algorithm && form.algorithm !== 'RS256') payload.algorithm = form.algorithm
  return payload
}

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
  letterSpacing: 0.4, color: '#6b7280', marginBottom: 4,
}
const inputStyle: React.CSSProperties = {
  width: '100%', fontSize: 13, fontFamily: 'inherit',
  border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px',
  boxSizing: 'border-box', background: '#fff',
}
const monoInputStyle: React.CSSProperties = {
  ...inputStyle,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
}

export function CredentialQuickCreateModal({ open, initialType, onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormState>(() => emptyForm(initialType))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setForm(emptyForm(initialType))
      setError(null)
    }
  }, [open, initialType])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const valid = useMemo(() => {
    if (!form.name.trim()) return false
    if (form.type === 'static_header') return !!form.header_name && !!form.header_value
    return !!form.client_id && !!form.token_endpoint && !!form.private_key
  }, [form])

  if (!open) return null

  const submit = async () => {
    setSaving(true)
    setError(null)
    try {
      const cred = await createCredential({
        name: form.name.trim(),
        type: form.type,
        description: form.description.trim() || undefined,
        payload: buildPayload(form),
      })
      onCreated(cred)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create credential')
    } finally {
      setSaving(false)
    }
  }

  // Portal to <body> so the overlay escapes the workflow editor's stacking
  // context — otherwise the left document panel renders on top of it.
  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.35)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 10000,
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="New credential"
        style={{
          backgroundColor: '#fff', borderRadius: 12, width: 560,
          maxHeight: '90vh', display: 'flex', flexDirection: 'column',
          boxShadow: '0 20px 60px rgba(0,0,0,0.18)',
        }}
      >
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid #e5e7eb',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#111827' }}>New credential</span>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#6b7280', display: 'flex' }}
          >
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>

        <div style={{ padding: '16px 20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label htmlFor="cred-name" style={labelStyle}>Name</label>
              <input
                id="cred-name"
                autoFocus
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Lakehouse OAuth"
                style={inputStyle}
              />
            </div>
            <div>
              <label htmlFor="cred-type" style={labelStyle}>Type</label>
              <select
                id="cred-type"
                value={form.type}
                onChange={e => setForm({ ...form, type: e.target.value as CredentialType })}
                style={inputStyle}
              >
                <option value="static_header">Static header</option>
                <option value="oauth_client_credentials">OAuth (client_credentials JWT)</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="cred-description" style={labelStyle}>Description</label>
            <input
              id="cred-description"
              type="text"
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="Optional"
              style={inputStyle}
            />
          </div>

          {form.type === 'static_header' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label htmlFor="cred-header-name" style={labelStyle}>Header name</label>
                <input
                  id="cred-header-name"
                  type="text"
                  value={form.header_name}
                  onChange={e => setForm({ ...form, header_name: e.target.value })}
                  placeholder="X-Api-Key"
                  style={monoInputStyle}
                />
              </div>
              <div>
                <label htmlFor="cred-header-value" style={labelStyle}>Header value</label>
                <input
                  id="cred-header-value"
                  type="password"
                  autoComplete="new-password"
                  data-1p-ignore
                  data-lpignore="true"
                  data-bwignore
                  name="vandalizer-credential-header-value"
                  value={form.header_value}
                  onChange={e => setForm({ ...form, header_value: e.target.value })}
                  placeholder="secret"
                  style={monoInputStyle}
                />
              </div>
            </div>
          )}

          {form.type === 'oauth_client_credentials' && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label htmlFor="cred-client-id" style={labelStyle}>Client ID</label>
                  <input
                    id="cred-client-id"
                    type="text"
                    value={form.client_id}
                    onChange={e => setForm({ ...form, client_id: e.target.value })}
                    style={monoInputStyle}
                  />
                </div>
                <div>
                  <label htmlFor="cred-token-endpoint" style={labelStyle}>Token endpoint</label>
                  <input
                    id="cred-token-endpoint"
                    type="url"
                    value={form.token_endpoint}
                    onChange={e => setForm({ ...form, token_endpoint: e.target.value })}
                    placeholder="https://issuer/oauth/token"
                    style={monoInputStyle}
                  />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                <div>
                  <label htmlFor="cred-scope" style={labelStyle}>Scope</label>
                  <input
                    id="cred-scope"
                    type="text"
                    value={form.scope}
                    onChange={e => setForm({ ...form, scope: e.target.value })}
                    placeholder="read write"
                    style={monoInputStyle}
                  />
                </div>
                <div>
                  <label htmlFor="cred-audience" style={labelStyle}>Audience</label>
                  <input
                    id="cred-audience"
                    type="text"
                    value={form.audience}
                    onChange={e => setForm({ ...form, audience: e.target.value })}
                    placeholder="(default: token endpoint)"
                    style={monoInputStyle}
                  />
                </div>
                <div>
                  <label htmlFor="cred-algorithm" style={labelStyle}>Algorithm</label>
                  <select
                    id="cred-algorithm"
                    value={form.algorithm}
                    onChange={e => setForm({ ...form, algorithm: e.target.value })}
                    style={inputStyle}
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
                <label htmlFor="cred-private-key" style={labelStyle}>Private key (PEM)</label>
                <textarea
                  id="cred-private-key"
                  value={form.private_key}
                  onChange={e => setForm({ ...form, private_key: e.target.value })}
                  rows={7}
                  placeholder={'-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----'}
                  style={{ ...monoInputStyle, fontSize: 12, resize: 'vertical' }}
                />
              </div>
            </>
          )}

          {error && (
            <div role="alert" style={{
              borderRadius: 6, border: '1px solid #fecaca', background: '#fef2f2',
              padding: '8px 10px', fontSize: 12, color: '#b91c1c',
            }}>
              {error}
            </div>
          )}

          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
            Secrets are encrypted at rest and never returned to the client after creation.
          </div>
        </div>

        <div style={{
          padding: '12px 20px', borderTop: '1px solid #e5e7eb',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
        }}>
          <a
            href="/credentials"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 12, color: '#6b7280', textDecoration: 'underline' }}
          >
            Manage all credentials →
          </a>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                border: '1px solid #d1d5db', background: '#fff', color: '#374151',
                fontSize: 13, fontWeight: 500, padding: '7px 14px', borderRadius: 6, cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={!valid || saving}
              style={{
                border: 'none',
                background: !valid || saving ? '#9ca3af' : 'var(--highlight-color, #2563eb)',
                color: 'var(--highlight-text, #fff)',
                fontSize: 13, fontWeight: 600, padding: '7px 14px', borderRadius: 6,
                cursor: !valid || saving ? 'not-allowed' : 'pointer',
              }}
            >
              {saving ? 'Saving…' : 'Save credential'}
            </button>
          </div>
        </div>
      </div>
      </FocusTrap>
    </div>,
    document.body,
  )
}
