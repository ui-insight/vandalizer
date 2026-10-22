import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { downloadPreservedCertificate, getCredentials, type PreservedCredential } from '../../api/certification'
import { CredentialScopeDescription } from './CredentialScopeDescription'

export function CredentialHistory({ refreshKey }: { refreshKey: string }) {
  const headingId = useId()
  const [credentials, setCredentials] = useState<PreservedCredential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)
  const request = useRef(0)
  const cancelPendingReads = useCallback(() => { ++request.current }, [])
  const refresh = useCallback(async () => {
    const version = ++request.current
    setLoading(true)
    try {
      const result = await getCredentials()
      if (version !== request.current) return
      setCredentials(result.credentials)
      setError(null)
    } catch {
      if (version === request.current) setError('Your certificate history could not be loaded.')
    } finally { if (version === request.current) setLoading(false) }
  }, [])
  useEffect(() => {
    void refresh()
    return cancelPendingReads
  }, [refresh, refreshKey, cancelPendingReads])

  const download = async (credential: PreservedCredential) => {
    setDownloading(credential.credential_id)
    setError(null)
    try { await downloadPreservedCertificate(credential.credential_id) }
    catch (error) { setError(error instanceof Error ? error.message : 'The certificate could not be downloaded.') }
    finally { setDownloading(null) }
  }

  return <section className="my-4 rounded-lg border border-gray-200 bg-white p-4" aria-labelledby={headingId}>
    <h3 id={headingId} className="text-sm font-semibold text-gray-900">Your earned certificates</h3>
    <p className="mt-1 text-sm text-gray-600">Previously earned certificates stay available when you choose another course.</p>
    {loading && <p className="mt-2 text-sm text-gray-600" role="status">Loading certificate history…</p>}
    {error && <div className="mt-2 text-sm text-red-800" role="alert">{error} <button type="button" className="underline font-medium" onClick={() => { void refresh() }}>Refresh certificate history</button></div>}
    {!loading && !error && credentials.length === 0 && <p className="mt-2 text-sm text-gray-600">No preserved certificates are available yet.</p>}
    <ul className="mt-3 space-y-3">
      {credentials.map(credential => <li key={credential.credential_id} className="rounded border border-gray-200 p-3">
        <p className="text-sm font-semibold text-gray-900 break-words">{credential.course_title}</p>
        <p className="mt-1 text-sm text-gray-600">{credential.certified_at ? `Earned ${credential.certified_at.slice(0, 10)}` : 'Original date unavailable'}{credential.course_version ? ` · ${credential.course_version}` : ''}</p>
        {credential.credential_scope && <details className="mt-2 min-w-0">
          <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-gray-900">Recorded certificate scope</summary>
          <CredentialScopeDescription scope={credential.credential_scope} />
        </details>}
        <button type="button" disabled={downloading !== null} onClick={() => { void download(credential) }} className="mt-2 rounded border border-gray-300 px-3 py-2 text-sm font-medium text-gray-800 disabled:opacity-50" aria-label={`Download certificate for ${credential.course_title}`}>
          {downloading === credential.credential_id ? 'Downloading…' : 'Download certificate (PDF)'}
        </button>
      </li>)}
    </ul>
  </section>
}
