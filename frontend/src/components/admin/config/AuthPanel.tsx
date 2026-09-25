import { useState } from 'react'
import { Lock, Plus, Globe, Pencil, Trash2 } from 'lucide-react'
import { useConfirm } from '../../shared/useConfirm'
import {
  getSystemConfig, addOAuthProvider, updateOAuthProvider, deleteOAuthProvider,
  updateAuthMethods, parseSamlMetadata,
} from '../../../api/admin'
import type { SystemConfigData } from '../../../api/admin'
import { sectionStyle, sectionHeaderStyle, sectionBodyStyle, labelStyle, inputStyle, checkStyle } from './styles'

// ──────────────────────────────────────────
// Authentication + OAuth / SAML providers
// ──────────────────────────────────────────

export interface AuthPanelProps {
  providers: SystemConfigData['oauth_providers']
  /** Seeds the checkbox row from the loaded config. The panel owns the value
   *  from then on; a failed reload unmounts this subtree, so a later config
   *  refresh (e.g. after adding a provider) must not reset the admin's
   *  in-progress selection — which is why this is an initial value, not a
   *  controlled one. */
  initialAuthMethods: string[]
  /** Provider writes re-read the whole config; hand the fresh copy back. */
  onConfigReplace: (config: SystemConfigData) => void
  /** Enabling a login path can clear a setup blocker. */
  onReadinessChange: () => void
  /** The tab-level error banner. */
  onError: (message: string | null) => void
}

export function AuthPanel({
  providers, initialAuthMethods, onConfigReplace, onReadinessChange, onError,
}: AuthPanelProps) {
  const confirm = useConfirm()

  // Auth
  const [authMethods, setAuthMethods] = useState<string[]>(initialAuthMethods)
  const [authSaving, setAuthSaving] = useState(false)

  // Add/edit provider form
  const [showAddProvider, setShowAddProvider] = useState(false)
  const [newProvider, setNewProvider] = useState({ provider: 'oauth', display_name: '', client_id: '', client_secret: '', redirect_uri: '', tenant_id: '', idp_entity_id: '', idp_sso_url: '', idp_x509_cert: '', jit_provisioning: true })
  // Holds the id of the provider being edited (never a list index/position)
  // — delete and edit are both reachable at once, so a position could drift
  // out from under an open form the moment another delete reshuffles the
  // list. See handleUpdateProvider.
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null)
  const [editingProvider, setEditingProvider] = useState({ provider: 'oauth', display_name: '', client_id: '', client_secret: '', redirect_uri: '', tenant_id: '', idp_entity_id: '', idp_sso_url: '', idp_x509_cert: '', jit_provisioning: true })
  const [samlMeta, setSamlMeta] = useState('')
  const [samlMetaBusy, setSamlMetaBusy] = useState(false)
  const [samlMetaError, setSamlMetaError] = useState('')
  const [providerError, setProviderError] = useState('')

  /** Return a message if the provider form is missing a required field, else ''. */
  const providerValidationError = (p: { provider: string; display_name: string; client_id: string; idp_entity_id: string; idp_sso_url: string; idp_x509_cert: string }): string => {
    if (!p.display_name.trim()) return 'Display name is required.'
    if (p.provider === 'saml') {
      if (!p.idp_entity_id.trim() || !p.idp_sso_url.trim() || !p.idp_x509_cert.trim()) {
        return 'SAML requires the IdP Entity ID, SSO URL, and x509 certificate (use "Fetch & fill" to import them).'
      }
    } else if (!p.client_id.trim()) {
      return 'Client ID is required.'
    }
    return ''
  }

  const handleImportSamlMetadata = async () => {
    const raw = samlMeta.trim()
    if (!raw) return
    setSamlMetaBusy(true)
    setSamlMetaError('')
    try {
      const body = raw.startsWith('<') ? { metadata_xml: raw } : { metadata_url: raw }
      const idp = await parseSamlMetadata(body)
      setNewProvider(p => ({ ...p, idp_entity_id: idp.idp_entity_id, idp_sso_url: idp.idp_sso_url, idp_x509_cert: idp.idp_x509_cert }))
    } catch (e) {
      setSamlMetaError(e instanceof Error ? e.message : 'Could not read metadata')
    } finally {
      setSamlMetaBusy(false)
    }
  }

  const handleSaveAuthMethods = async () => {
    setAuthSaving(true)
    onError(null)
    try {
      await updateAuthMethods(authMethods)
      onReadinessChange()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to update auth methods')
    } finally {
      setAuthSaving(false)
    }
  }

  const handleAddProvider = async () => {
    const validationError = providerValidationError(newProvider)
    if (validationError) { setProviderError(validationError); return }
    setProviderError('')
    try {
      await addOAuthProvider(newProvider as unknown as Record<string, unknown>)
      // Refresh config
      const c = await getSystemConfig()
      onConfigReplace(c)
      setNewProvider({ provider: 'oauth', display_name: '', client_id: '', client_secret: '', redirect_uri: '', tenant_id: '', idp_entity_id: '', idp_sso_url: '', idp_x509_cert: '', jit_provisioning: true })
      setSamlMeta('')
      setShowAddProvider(false)
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : 'Failed to add provider')
    }
  }

  const handleDeleteProvider = async (index: number) => {
    const provider = providers[index] as Record<string, unknown> | undefined
    const name = (provider?.display_name as string) || (provider?.provider as string) || 'this provider'
    const ok = await confirm({
      title: 'Delete OAuth provider?',
      message: (
        <>
          Are you sure you want to delete <strong>{name}</strong>? Users authenticating through this provider will no longer be able to sign in via it.
        </>
      ),
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    const providerId = provider?.id as string | undefined
    if (!providerId) {
      onError('Could not find the provider to delete — refresh and try again.')
      return
    }
    try {
      await deleteOAuthProvider(providerId)
      const c = await getSystemConfig()
      onConfigReplace(c)
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to delete provider')
    }
  }

  const handleEditProvider = (index: number) => {
    const p = providers[index] as Record<string, unknown> | undefined
    if (!p) return
    const providerId = p.id as string | undefined
    if (!providerId) {
      onError('Could not find the provider to edit — refresh and try again.')
      return
    }
    setProviderError('')
    setEditingProviderId(providerId)
    setEditingProvider({
      provider: (p.provider as string) || 'oauth',
      display_name: (p.display_name as string) || '',
      client_id: (p.client_id as string) || '',
      client_secret: '***',
      redirect_uri: (p.redirect_uri as string) || '',
      tenant_id: (p.tenant_id as string) || '',
      idp_entity_id: (p.idp_entity_id as string) || '',
      idp_sso_url: (p.idp_sso_url as string) || '',
      idp_x509_cert: (p.idp_x509_cert as string) || '',
      // Absent on providers saved before the field existed = enabled.
      jit_provisioning: p.jit_provisioning !== false,
    })
    setShowAddProvider(false)
  }

  const handleUpdateProvider = async () => {
    if (editingProviderId === null) return
    const validationError = providerValidationError(editingProvider)
    if (validationError) { setProviderError(validationError); return }
    // The held id may no longer be in the list — e.g. another delete while
    // this form was open. Refuse rather than resolving to whatever now sits
    // at some stale position.
    const stillExists = providers.some(pr => (pr as Record<string, unknown>).id === editingProviderId)
    if (!stillExists) {
      setProviderError('Could not find the provider to update — refresh and try again.')
      return
    }
    setProviderError('')
    try {
      await updateOAuthProvider(editingProviderId, editingProvider as unknown as Record<string, unknown>)
      const c = await getSystemConfig()
      onConfigReplace(c)
      setEditingProviderId(null)
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : 'Failed to update provider')
    }
  }

  return (
    <div id="cfg-auth" style={sectionStyle}>
      <div style={sectionHeaderStyle}>
        <Lock size={18} color="#6b7280" /> Authentication
      </div>
      <div style={sectionBodyStyle}>
        <div style={{ marginBottom: 20 }}>
          <label style={labelStyle}>Auth Methods</label>
          <div style={{ display: 'flex', gap: 16 }}>
            {['password', 'oauth'].map(m => {
              // Disable unchecking the last remaining method — an empty
              // auth_methods list disables every login path with no
              // in-app recovery. The server also rejects this, but the
              // UI should never let an admin walk into that footgun.
              const isLastMethod = authMethods.length === 1 && authMethods.includes(m)
              return (
                <label
                  key={m}
                  style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: isLastMethod ? 'not-allowed' : 'pointer', textTransform: 'capitalize' }}
                >
                  <input
                    type="checkbox"
                    checked={authMethods.includes(m)}
                    disabled={isLastMethod}
                    title={isLastMethod ? 'At least one auth method must remain enabled' : undefined}
                    onChange={e => {
                      if (e.target.checked) setAuthMethods(prev => [...prev, m])
                      else setAuthMethods(prev => prev.filter(x => x !== m))
                    }}
                    style={checkStyle}
                  />
                  {m === 'oauth' ? 'OAuth / SAML' : m}
                </label>
              )
            })}
          </div>
          <button
            onClick={handleSaveAuthMethods}
            disabled={authSaving}
            style={{
              marginTop: 12, padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
              fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
            }}
          >
            {authSaving ? 'Saving...' : 'Update Methods'}
          </button>
        </div>

        {/* OAuth Providers */}
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <label style={{ ...labelStyle, marginBottom: 0 }}>OAuth / SAML Providers</label>
            <button
              onClick={() => setShowAddProvider(!showAddProvider)}
              style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px',
                borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
              }}
            >
              <Plus size={14} /> Add Provider
            </button>
          </div>

          {providers && providers.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {providers.map((p, i) => {
                const providerId = (p as Record<string, unknown>).id as string | undefined
                const isEditingThisRow = providerId !== undefined && editingProviderId === providerId
                return (
                <div key={i}>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 16px', background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)',
                    border: '1px solid #e5e7eb',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Globe size={16} color="#6b7280" />
                      <span style={{ fontSize: 14, fontWeight: 500 }}>{(p as Record<string, unknown>).display_name as string || (p as Record<string, unknown>).provider as string}</span>
                      <span style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#dbeafe', color: '#1e40af', fontWeight: 600,
                      }}>
                        {((p as Record<string, unknown>).provider as string || 'oauth').toUpperCase()}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button
                        type="button"
                        aria-label="Edit provider"
                        onClick={() => isEditingThisRow ? setEditingProviderId(null) : handleEditProvider(i)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
                      >
                        <Pencil size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label="Delete provider"
                        onClick={() => handleDeleteProvider(i)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                  {isEditingThisRow && (
                    <div style={{ marginTop: 8, padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb' }}>
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Edit Provider</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        <div>
                          <label htmlFor={`admin-oauth-edit-${i}-type`} style={labelStyle}>Type</label>
                          <select
                            id={`admin-oauth-edit-${i}-type`}
                            value={editingProvider.provider}
                            onChange={e => setEditingProvider({ ...editingProvider, provider: e.target.value })}
                            style={inputStyle}
                          >
                            <option value="oauth">OAuth 2.0</option>
                            <option value="azure">Azure AD</option>
                            <option value="saml">SAML</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor={`admin-oauth-edit-${i}-display-name`} style={labelStyle}>Display Name</label>
                          <input id={`admin-oauth-edit-${i}-display-name`} value={editingProvider.display_name} onChange={e => setEditingProvider({ ...editingProvider, display_name: e.target.value })} style={inputStyle} />
                        </div>
                        {editingProvider.provider !== 'saml' && (
                          <>
                            <div>
                              <label htmlFor={`admin-oauth-edit-${i}-client-id`} style={labelStyle}>Client ID</label>
                              <input id={`admin-oauth-edit-${i}-client-id`} value={editingProvider.client_id} onChange={e => setEditingProvider({ ...editingProvider, client_id: e.target.value })} style={inputStyle} />
                            </div>
                            <div>
                              <label htmlFor={`admin-oauth-edit-${i}-client-secret`} style={labelStyle}>Client Secret</label>
                              <input id={`admin-oauth-edit-${i}-client-secret`} type="password" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore name="vandalizer-oauth-client-secret-edit" value={editingProvider.client_secret} onChange={e => setEditingProvider({ ...editingProvider, client_secret: e.target.value })} style={inputStyle} placeholder="Leave as *** to keep existing" />
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                              <label htmlFor={`admin-oauth-edit-${i}-redirect-uri`} style={labelStyle}>Redirect URI</label>
                              <input id={`admin-oauth-edit-${i}-redirect-uri`} value={editingProvider.redirect_uri} onChange={e => setEditingProvider({ ...editingProvider, redirect_uri: e.target.value })} style={inputStyle} />
                            </div>
                          </>
                        )}
                        {editingProvider.provider === 'azure' && (
                          <div style={{ gridColumn: '1 / -1' }}>
                            <label htmlFor={`admin-oauth-edit-${i}-tenant-id`} style={labelStyle}>Tenant ID</label>
                            <input id={`admin-oauth-edit-${i}-tenant-id`} value={editingProvider.tenant_id} onChange={e => setEditingProvider({ ...editingProvider, tenant_id: e.target.value })} style={inputStyle} />
                          </div>
                        )}
                        {editingProvider.provider === 'saml' && (
                          <>
                            <div style={{ gridColumn: '1 / -1' }}>
                              <label htmlFor={`admin-oauth-edit-${i}-idp-entity`} style={labelStyle}>IdP Entity ID</label>
                              <input id={`admin-oauth-edit-${i}-idp-entity`} value={editingProvider.idp_entity_id} onChange={e => setEditingProvider({ ...editingProvider, idp_entity_id: e.target.value })} style={inputStyle} />
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                              <label htmlFor={`admin-oauth-edit-${i}-idp-sso`} style={labelStyle}>IdP SSO URL</label>
                              <input id={`admin-oauth-edit-${i}-idp-sso`} value={editingProvider.idp_sso_url} onChange={e => setEditingProvider({ ...editingProvider, idp_sso_url: e.target.value })} style={inputStyle} />
                            </div>
                            <div style={{ gridColumn: '1 / -1' }}>
                              <label htmlFor={`admin-oauth-edit-${i}-idp-cert`} style={labelStyle}>IdP x509 Certificate</label>
                              <textarea id={`admin-oauth-edit-${i}-idp-cert`} value={editingProvider.idp_x509_cert} onChange={e => setEditingProvider({ ...editingProvider, idp_x509_cert: e.target.value })} style={{ ...inputStyle, minHeight: 90, fontFamily: 'monospace', fontSize: 11 }} />
                            </div>
                          </>
                        )}
                        <div style={{ gridColumn: '1 / -1' }}>
                          <label htmlFor={`admin-oauth-edit-${i}-jit`} style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer' }}>
                            <input
                              id={`admin-oauth-edit-${i}-jit`}
                              type="checkbox"
                              checked={editingProvider.jit_provisioning}
                              onChange={e => setEditingProvider({ ...editingProvider, jit_provisioning: e.target.checked })}
                              style={checkStyle}
                            />
                            Create accounts on first sign-in (JIT provisioning)
                          </label>
                          <div style={{ fontSize: 12, opacity: 0.7, marginTop: 2, marginLeft: 24 }}>
                            When off, sign-in is denied for users that don't already exist.
                          </div>
                        </div>
                      </div>
                      {providerError && (
                        <div role="alert" style={{ marginTop: 10, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#b91c1c', fontSize: 13 }}>
                          {providerError}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                        <button
                          onClick={handleUpdateProvider}
                          style={{
                            padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                            background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                          }}
                        >
                          Save Changes
                        </button>
                        <button
                          onClick={() => setEditingProviderId(null)}
                          style={{
                            padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                            background: '#fff', fontSize: 13, cursor: 'pointer',
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                )
              })}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#9ca3af', padding: '8px 0' }}>No providers configured.</div>
          )}

          {showAddProvider && (
            <div style={{ marginTop: 12, padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb' }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>New Provider</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Type</label>
                  <select
                    value={newProvider.provider}
                    onChange={e => setNewProvider({ ...newProvider, provider: e.target.value })}
                    style={inputStyle}
                  >
                    <option value="oauth">OAuth 2.0</option>
                    <option value="azure">Azure AD</option>
                    <option value="saml">SAML</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Display Name</label>
                  <input value={newProvider.display_name} onChange={e => setNewProvider({ ...newProvider, display_name: e.target.value })} style={inputStyle} />
                </div>
                {newProvider.provider !== 'saml' && (
                  <>
                    <div>
                      <label style={labelStyle}>Client ID</label>
                      <input value={newProvider.client_id} onChange={e => setNewProvider({ ...newProvider, client_id: e.target.value })} style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>Client Secret</label>
                      <input type="password" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore name="vandalizer-oauth-client-secret-new" value={newProvider.client_secret} onChange={e => setNewProvider({ ...newProvider, client_secret: e.target.value })} style={inputStyle} />
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>Redirect URI (set automatically; register this in your identity provider)</label>
                      <input value={`${window.location.origin}/api/auth/oauth/azure/callback`} readOnly style={{ ...inputStyle, opacity: 0.7, cursor: 'default' }} />
                    </div>
                  </>
                )}
                {newProvider.provider === 'azure' && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>Tenant ID</label>
                    <input value={newProvider.tenant_id} onChange={e => setNewProvider({ ...newProvider, tenant_id: e.target.value })} style={inputStyle} />
                  </div>
                )}
                {newProvider.provider === 'saml' && (
                  <>
                    <div style={{ gridColumn: '1 / -1', padding: 10, background: '#eef2ff', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #c7d2fe' }}>
                      <label style={labelStyle}>Import from IdP metadata (URL or paste XML) — auto-fills the fields below</label>
                      <textarea
                        value={samlMeta}
                        onChange={e => setSamlMeta(e.target.value)}
                        placeholder="https://idp.example.edu/idp/shibboleth  — or paste the metadata XML"
                        style={{ ...inputStyle, minHeight: 44 }}
                      />
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                        <button
                          type="button"
                          onClick={handleImportSamlMetadata}
                          disabled={samlMetaBusy || !samlMeta.trim()}
                          style={{ padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #6366f1', background: '#fff', color: '#4338ca', fontSize: 12, fontWeight: 600, cursor: samlMetaBusy || !samlMeta.trim() ? 'not-allowed' : 'pointer', opacity: samlMetaBusy || !samlMeta.trim() ? 0.6 : 1 }}
                        >
                          {samlMetaBusy ? 'Reading…' : 'Fetch & fill'}
                        </button>
                        {samlMetaError && <span role="alert" style={{ fontSize: 12, color: '#b91c1c' }}>{samlMetaError}</span>}
                      </div>
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>IdP Entity ID</label>
                      <input value={newProvider.idp_entity_id} onChange={e => setNewProvider({ ...newProvider, idp_entity_id: e.target.value })} style={inputStyle} placeholder="https://idp.example.edu/idp/shibboleth" />
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>IdP SSO URL</label>
                      <input value={newProvider.idp_sso_url} onChange={e => setNewProvider({ ...newProvider, idp_sso_url: e.target.value })} style={inputStyle} placeholder="https://idp.example.edu/idp/profile/SAML2/Redirect/SSO" />
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>IdP x509 Certificate</label>
                      <textarea value={newProvider.idp_x509_cert} onChange={e => setNewProvider({ ...newProvider, idp_x509_cert: e.target.value })} style={{ ...inputStyle, minHeight: 90, fontFamily: 'monospace', fontSize: 11 }} placeholder="-----BEGIN CERTIFICATE-----" />
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>Service Provider details (give these to your IdP administrator)</label>
                      <input value={`${window.location.origin}/api/auth/saml/metadata`} readOnly style={{ ...inputStyle, opacity: 0.7, cursor: 'default' }} />
                      <input value={`${window.location.origin}/api/auth/saml/acs`} readOnly style={{ ...inputStyle, opacity: 0.7, cursor: 'default', marginTop: 6 }} />
                    </div>
                  </>
                )}
                <div style={{ gridColumn: '1 / -1' }}>
                  <label htmlFor="admin-oauth-new-jit" style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer' }}>
                    <input
                      id="admin-oauth-new-jit"
                      type="checkbox"
                      checked={newProvider.jit_provisioning}
                      onChange={e => setNewProvider({ ...newProvider, jit_provisioning: e.target.checked })}
                      style={checkStyle}
                    />
                    Create accounts on first sign-in (JIT provisioning)
                  </label>
                  <div style={{ fontSize: 12, opacity: 0.7, marginTop: 2, marginLeft: 24 }}>
                    When off, sign-in is denied for users that don't already exist.
                  </div>
                </div>
              </div>
              {providerError && (
                <div role="alert" style={{ marginTop: 10, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#b91c1c', fontSize: 13 }}>
                  {providerError}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button
                  onClick={handleAddProvider}
                  style={{
                    padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                    background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  Add Provider
                </button>
                <button
                  onClick={() => setShowAddProvider(false)}
                  style={{
                    padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                    background: '#fff', fontSize: 13, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
