import { useState } from 'react'
import { downloadCertificate, downloadPreservedCertificate, getCredentials } from '../../api/certification'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { CredentialHistory } from '../certification/CredentialHistory'

/** Certificate reads must use the card's earned course, never today's selection. */
export function ChatCertificateAccess({ enrollmentId }: { enrollmentId?: string }) {
  const certification = useCertificationPanelOptional()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const ambiguous = !enrollmentId && (!certification?.progress || !!certification.progress.enrollment_id)
  const download = async () => {
    setBusy(true)
    setError(null)
    try {
      if (enrollmentId) {
        const { credentials } = await getCredentials()
        const matches = credentials.filter(credential => credential.enrollment_id === enrollmentId)
        if (matches.length !== 1) throw new Error('The original certificate is not available yet. Check saved course progress before trying again.')
        await downloadPreservedCertificate(matches[0].credential_id)
      } else {
        await downloadCertificate()
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The certificate could not be downloaded. Try again.')
    } finally { setBusy(false) }
  }

  return <div className="mt-3">
    {ambiguous ? <>
      <p className="text-sm text-gray-700">This older card does not identify its course. Choose the earned certificate from your history.</p>
      <button type="button" className="mt-2 rounded border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800" aria-expanded={showHistory} onClick={() => setShowHistory(value => !value)}>View earned certificates</button>
      {showHistory && <CredentialHistory refreshKey="chat-certificate-history" />}
    </> : <>
      <p className="text-sm text-gray-700">Your certificate records this course’s requirements. Keep it with your training records.</p>
      <button type="button" disabled={busy} className="mt-2 rounded border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 disabled:opacity-50" onClick={() => void download()}>
        {busy ? 'Preparing certificate…' : 'Download certificate (PDF)'}
      </button>
      {busy && <span role="status" className="sr-only">Preparing certificate download.</span>}
      {error && <p role="alert" className="mt-2 text-sm text-red-800">{error}</p>}
    </>}
  </div>
}
