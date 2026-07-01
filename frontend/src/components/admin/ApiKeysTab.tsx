import { useCallback, useEffect, useState } from 'react'
import { BookOpen, Copy, Download, KeyRound, Plus, Sparkles, Trash2, X } from 'lucide-react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

import {
  API_KEY_SKILL_DOWNLOAD_URL,
  createApiKey,
  getApiKeyDocs,
  listApiKeys,
  MGMT_SCOPE_OPTIONS,
  revokeApiKey,
  type ApiKeyListItem,
  type CreateApiKeyResponse,
} from '../../api/admin'

marked.setOptions({ breaks: true, gfm: true })

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = iso.endsWith('Z') || iso.includes('+') ? new Date(iso) : new Date(iso + 'Z')
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function isExpired(key: ApiKeyListItem): boolean {
  if (!key.expires_at) return false
  const exp = key.expires_at.endsWith('Z') ? new Date(key.expires_at) : new Date(key.expires_at + 'Z')
  return exp < new Date()
}

function StatusBadge({ keyItem }: { keyItem: ApiKeyListItem }) {
  let label = 'Active'
  let bg = '#dcfce7'
  let fg = '#166534'
  if (keyItem.revoked_at) {
    label = 'Revoked'
    bg = '#fee2e2'
    fg = '#991b1b'
  } else if (isExpired(keyItem)) {
    label = 'Expired'
    bg = '#fef3c7'
    fg = '#92400e'
  }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
      fontSize: 12, fontWeight: 600, backgroundColor: bg, color: fg,
    }}>
      {label}
    </span>
  )
}

export function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKeyListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [includeRevoked, setIncludeRevoked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createdKey, setCreatedKey] = useState<CreateApiKeyResponse | null>(null)
  const [showDocs, setShowDocs] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listApiKeys(includeRevoked)
      setKeys(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load keys')
    } finally {
      setLoading(false)
    }
  }, [includeRevoked])

  useEffect(() => {
    void reload()
  }, [reload])

  const handleRevoke = async (keyId: string, name: string) => {
    if (!confirm(`Revoke API key "${name}"? This is immediate and cannot be undone.`)) return
    try {
      await revokeApiKey(keyId)
      await reload()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Revoke failed')
    }
  }

  return (
    <div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 24,
      }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Management API keys</h2>
          <p style={{ fontSize: 14, color: '#6b7280' }}>
            Scoped, named keys for service consumers (dashboards, agentic tooling).
            Mounted under <code>/api/mgmt/v1</code>.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <a
            href={API_KEY_SKILL_DOWNLOAD_URL}
            download="SKILL.md"
            title="Download a Claude Code skill that drives this API from any terminal"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', borderRadius: 6,
              backgroundColor: 'transparent', color: '#374151',
              border: '1px solid #d1d5db', fontWeight: 600,
              cursor: 'pointer', textDecoration: 'none',
            }}
          >
            <Download size={16} /> Claude Code skill
          </a>
          <button
            onClick={() => setShowDocs(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', borderRadius: 6,
              backgroundColor: 'transparent', color: '#374151',
              border: '1px solid #d1d5db', fontWeight: 600, cursor: 'pointer',
            }}
          >
            <BookOpen size={16} /> View documentation
          </button>
          <button
            onClick={() => setShowCreate(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', borderRadius: 6,
              backgroundColor: 'var(--highlight-color, #3b82f6)', color: 'white',
              border: 'none', fontWeight: 600, cursor: 'pointer',
            }}
          >
            <Plus size={16} /> New key
          </button>
        </div>
      </div>

      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 12, fontSize: 13 }}>
        <input
          type="checkbox"
          checked={includeRevoked}
          onChange={e => setIncludeRevoked(e.target.checked)}
        />
        Show revoked keys
      </label>

      {error && (
        <div style={{
          padding: 12, marginBottom: 16, borderRadius: 6,
          backgroundColor: '#fee2e2', color: '#991b1b', fontSize: 13,
        }}>{error}</div>
      )}

      {loading ? (
        <p style={{ color: '#6b7280' }}>Loading…</p>
      ) : keys.length === 0 ? (
        <div style={{
          padding: 32, textAlign: 'center', borderRadius: 6,
          border: '1px dashed #d1d5db', color: '#6b7280',
        }}>
          <KeyRound size={28} style={{ marginBottom: 8 }} />
          <p>No API keys yet. Create one to give an external service or agentic tool access.</p>
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
              <th style={{ padding: 8 }}>Name</th>
              <th style={{ padding: 8 }}>Prefix</th>
              <th style={{ padding: 8 }}>Scopes</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Created</th>
              <th style={{ padding: 8 }}>Last used</th>
              <th style={{ padding: 8 }}>Expires</th>
              <th style={{ padding: 8 }} />
            </tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: 8, fontWeight: 600 }}>
                  {k.name}
                  {k.description && (
                    <div style={{ fontSize: 12, color: '#6b7280', fontWeight: 400 }}>
                      {k.description}
                    </div>
                  )}
                </td>
                <td style={{ padding: 8, fontFamily: 'monospace', fontSize: 12 }}>
                  {k.prefix}…
                </td>
                <td style={{ padding: 8 }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {k.scopes.map(s => (
                      <span key={s} style={{
                        fontSize: 11, padding: '2px 6px', borderRadius: 4,
                        backgroundColor: '#f3f4f6', fontFamily: 'monospace',
                      }}>{s}</span>
                    ))}
                  </div>
                </td>
                <td style={{ padding: 8 }}><StatusBadge keyItem={k} /></td>
                <td style={{ padding: 8, color: '#6b7280' }}>{fmtDate(k.created_at)}</td>
                <td style={{ padding: 8, color: '#6b7280' }}>
                  {fmtDate(k.last_used_at)}
                  {k.last_used_ip && (
                    <div style={{ fontSize: 11, fontFamily: 'monospace' }}>{k.last_used_ip}</div>
                  )}
                </td>
                <td style={{ padding: 8, color: '#6b7280' }}>{fmtDate(k.expires_at)}</td>
                <td style={{ padding: 8 }}>
                  {!k.revoked_at && (
                    <button
                      onClick={() => handleRevoke(k.id, k.name)}
                      style={{
                        padding: 6, border: 'none', background: 'transparent',
                        color: '#dc2626', cursor: 'pointer',
                      }}
                      title="Revoke"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showCreate && (
        <CreateKeyModal
          onClose={() => setShowCreate(false)}
          onCreated={created => {
            setShowCreate(false)
            setCreatedKey(created)
            void reload()
          }}
        />
      )}

      {createdKey && (
        <TokenRevealModal
          created={createdKey}
          onClose={() => setCreatedKey(null)}
        />
      )}

      {showDocs && <DocsModal onClose={() => setShowDocs(false)} />}
    </div>
  )
}

function DocsModal({ onClose }: { onClose: () => void }) {
  const [html, setHtml] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getApiKeyDocs()
      .then(res => {
        if (cancelled) return
        const rendered = DOMPurify.sanitize(marked.parse(res.markdown) as string)
        setHtml(rendered)
      })
      .catch(e => {
        if (cancelled) return
        setErr(e instanceof Error ? e.message : 'Failed to load documentation')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: 'white', borderRadius: 10,
        maxWidth: 1080, width: '94%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
        overflow: 'hidden',
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '16px 24px', borderBottom: '1px solid #e5e7eb',
          flexShrink: 0, backgroundColor: '#fafafa',
        }}>
          <div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: '#111827' }}>
              Management API documentation
            </h3>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
              Mounted at <code style={{
                fontFamily: 'ui-monospace, monospace', fontSize: 12,
                backgroundColor: '#fff', padding: '1px 6px', borderRadius: 4,
                border: '1px solid #e5e7eb',
              }}>/api/mgmt/v1</code> · scoped, named keys · audited
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close documentation"
            style={{
              padding: 6, border: 'none', background: 'transparent',
              cursor: 'pointer', color: '#6b7280', borderRadius: 4,
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{
          overflowY: 'auto', padding: '20px 28px',
        }}>
          <SkillCallout />
          {err ? (
            <div style={{
              padding: 12, borderRadius: 6,
              backgroundColor: '#fee2e2', color: '#991b1b', fontSize: 13,
            }}>{err}</div>
          ) : html === null ? (
            <p style={{ color: '#6b7280' }}>Loading…</p>
          ) : (
            <div className="mgmt-docs" dangerouslySetInnerHTML={{ __html: html }} />
          )}
        </div>
      </div>
    </div>
  )
}

function SkillCallout() {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 14,
      padding: 16, marginBottom: 22,
      borderRadius: 8,
      background: 'linear-gradient(135deg, #fefce8 0%, #fef9c3 100%)',
      border: '1px solid #fde68a',
    }}>
      <div style={{
        flexShrink: 0, width: 36, height: 36, borderRadius: 8,
        backgroundColor: '#fde68a', color: '#92400e',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Sparkles size={18} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#78350f', marginBottom: 4 }}>
          Use this API from Claude Code in one command
        </div>
        <div style={{ fontSize: 13, color: '#92400e', lineHeight: 1.5, marginBottom: 10 }}>
          Download the bundled skill, drop it in <code style={{
            fontFamily: 'ui-monospace, monospace', fontSize: 12,
            backgroundColor: '#ffffff', padding: '1px 5px', borderRadius: 3,
            border: '1px solid #fde68a',
          }}>~/.claude/skills/vandalizer-api/SKILL.md</code>, then type{' '}
          <code style={{
            fontFamily: 'ui-monospace, monospace', fontSize: 12,
            backgroundColor: '#ffffff', padding: '1px 5px', borderRadius: 3,
            border: '1px solid #fde68a',
          }}>/vandalizer-api</code> in any session. It prompts you for a server
          and key, saves them locally, and translates plain-English asks into
          calls against this API.
        </div>
        <a
          href={API_KEY_SKILL_DOWNLOAD_URL}
          download="SKILL.md"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 6,
            backgroundColor: '#92400e', color: '#fffbeb',
            fontWeight: 600, fontSize: 13,
            textDecoration: 'none',
          }}
        >
          <Download size={14} /> Download SKILL.md
        </a>
      </div>
    </div>
  )
}

function CreateKeyModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (k: CreateApiKeyResponse) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [scopes, setScopes] = useState<string[]>(['metrics:read'])
  const [expiresAt, setExpiresAt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const toggle = (scope: string) => {
    setScopes(prev => prev.includes(scope) ? prev.filter(s => s !== scope) : [...prev, scope])
  }

  const submit = async () => {
    setErr(null)
    if (!name.trim()) {
      setErr('Name is required')
      return
    }
    if (scopes.length === 0) {
      setErr('At least one scope is required')
      return
    }
    setSubmitting(true)
    try {
      const created = await createApiKey({
        name: name.trim(),
        scopes,
        description: description.trim() || undefined,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      })
      onCreated(created)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create key')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ModalShell onClose={onClose} title="Create management API key">
      {err && (
        <div style={{
          padding: 8, marginBottom: 12, borderRadius: 4,
          backgroundColor: '#fee2e2', color: '#991b1b', fontSize: 13,
        }}>{err}</div>
      )}

      <label htmlFor="apikey-name" style={{ display: 'block', marginBottom: 12 }}>
        <span style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Name</span>
        <input
          id="apikey-name"
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. claude-code-readonly"
          style={inputStyle}
        />
      </label>

      <label htmlFor="apikey-description" style={{ display: 'block', marginBottom: 12 }}>
        <span style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Description (optional)</span>
        <input
          id="apikey-description"
          type="text"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="What is this key for?"
          style={inputStyle}
        />
      </label>

      <div style={{ marginBottom: 12 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          marginBottom: 6,
        }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Scopes</span>
          <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
            <button
              type="button"
              onClick={() => setScopes([...MGMT_SCOPE_OPTIONS])}
              disabled={scopes.length === MGMT_SCOPE_OPTIONS.length}
              style={linkButtonStyle}
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() => setScopes([])}
              disabled={scopes.length === 0}
              style={linkButtonStyle}
            >
              Clear
            </button>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6 }}>
          {MGMT_SCOPE_OPTIONS.map(s => (
            <label key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
              <input
                type="checkbox"
                checked={scopes.includes(s)}
                onChange={() => toggle(s)}
              />
              <code style={{ fontSize: 12 }}>{s}</code>
            </label>
          ))}
        </div>
        <p style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
          Action scopes (<code>:run</code>, <code>:write</code>) spend tokens or mutate state — issue
          read-only first and add the rest only after review.
        </p>
      </div>

      <label htmlFor="apikey-expires-at" style={{ display: 'block', marginBottom: 16 }}>
        <span style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
          Expires at (optional)
        </span>
        <input
          id="apikey-expires-at"
          type="datetime-local"
          value={expiresAt}
          onChange={e => setExpiresAt(e.target.value)}
          style={inputStyle}
        />
      </label>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button onClick={onClose} style={cancelButtonStyle}>Cancel</button>
        <button
          onClick={submit}
          disabled={submitting}
          style={{ ...primaryButtonStyle, opacity: submitting ? 0.6 : 1 }}
        >
          {submitting ? 'Creating…' : 'Create key'}
        </button>
      </div>
    </ModalShell>
  )
}

function TokenRevealModal({
  created,
  onClose,
}: {
  created: CreateApiKeyResponse
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(created.token)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <ModalShell onClose={onClose} title="Copy your token now">
      <div style={{
        padding: 12, marginBottom: 16, borderRadius: 6,
        backgroundColor: '#fef3c7', color: '#92400e', fontSize: 13,
      }}>
        <strong>This is the only time the full token will be shown.</strong> Copy and store it
        somewhere safe (a secrets manager, a `.env` file, etc.). After you close this dialog
        you can only see the prefix.
      </div>

      <div style={{
        padding: 12, marginBottom: 12, borderRadius: 6,
        backgroundColor: '#f3f4f6', fontFamily: 'monospace', fontSize: 13,
        wordBreak: 'break-all',
      }}>
        {created.token}
      </div>

      <button
        onClick={copy}
        style={{
          ...primaryButtonStyle,
          display: 'inline-flex', alignItems: 'center', gap: 6,
        }}
      >
        <Copy size={16} /> {copied ? 'Copied' : 'Copy token'}
      </button>

      <div style={{ marginTop: 16, fontSize: 13, color: '#6b7280' }}>
        Use it as: <code>X-API-Key: {created.token.slice(0, 12)}…</code>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
        <button onClick={onClose} style={cancelButtonStyle}>Close</button>
      </div>
    </ModalShell>
  )
}

function ModalShell({
  onClose,
  title,
  children,
}: {
  onClose: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: 'white', borderRadius: 8, padding: 24,
        maxWidth: 560, width: '90%', maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700 }}>{title}</h3>
          <button onClick={onClose} style={{
            padding: 4, border: 'none', background: 'transparent', cursor: 'pointer',
          }}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 6,
  border: '1px solid #d1d5db', fontSize: 14,
}

const primaryButtonStyle: React.CSSProperties = {
  padding: '8px 14px', borderRadius: 6,
  backgroundColor: 'var(--highlight-color, #3b82f6)', color: 'white',
  border: 'none', fontWeight: 600, cursor: 'pointer',
}

const cancelButtonStyle: React.CSSProperties = {
  padding: '8px 14px', borderRadius: 6,
  backgroundColor: 'transparent', color: '#374151',
  border: '1px solid #d1d5db', fontWeight: 600, cursor: 'pointer',
}

const linkButtonStyle: React.CSSProperties = {
  padding: 0, border: 'none', background: 'transparent',
  color: 'var(--highlight-color, #3b82f6)', fontWeight: 600,
  cursor: 'pointer',
}
