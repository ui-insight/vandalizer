import { useState } from 'react'
import { CheckCircle, XCircle, Loader2, Plug } from 'lucide-react'
import type { CredentialTestResult } from '../../types/credential'

/**
 * "Test" for a credential: runs the same path an API Node takes (validate →
 * obtain the auth, a real token exchange for OAuth → optionally one GET with
 * it) and shows each step with the reason it failed, so a connection problem
 * is debugged where the credential is entered rather than by running a
 * workflow and reading a step error. Secrets never appear in the report.
 *
 * `run` is supplied by the host: a draft test for unsaved forms, a saved-
 * credential test (with any unsaved edits merged in) otherwise.
 */
interface Props {
  run: (testUrl: string) => Promise<CredentialTestResult>
  testUrl: string
  onTestUrlChange: (url: string) => void
  /** Hide the URL field (e.g. a compact row action that uses the stored URL). */
  hideUrlField?: boolean
  disabled?: boolean
  compact?: boolean
}

export function summarizeTest(result: CredentialTestResult): string {
  if (result.ok) {
    return result.status_code != null
      ? `Connection works — the test request returned ${result.status_code}.`
      : 'Credential works. Add a test URL to try a real request with it.'
  }
  const failed = result.steps.find(s => !s.ok)
  return failed ? `${failed.step} failed.` : 'Test failed.'
}

export function CredentialTestPanel({ run, testUrl, onTestUrlChange, hideUrlField, disabled, compact }: Props) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<CredentialTestResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleTest = async () => {
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      setResult(await run(testUrl.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not run the test')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {!hideUrlField && (
          <input
            aria-label="Test URL"
            type="url"
            value={testUrl}
            onChange={e => onTestUrlChange(e.target.value)}
            placeholder="Test URL (optional) — e.g. https://api.example.com/v1/me"
            disabled={disabled}
            style={{
              flex: 1, minWidth: 220, padding: '6px 10px', fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, outline: 'none', boxSizing: 'border-box',
            }}
          />
        )}
        <button
          type="button"
          onClick={handleTest}
          disabled={disabled || running}
          title="Try this credential now: obtain the auth and, with a test URL, send one GET request"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, padding: compact ? '4px 10px' : '6px 12px',
            fontSize: compact ? 12 : 13, fontWeight: 600, fontFamily: 'inherit',
            border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff', color: '#374151',
            cursor: disabled || running ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
          }}
        >
          {running ? <Loader2 style={{ width: 13, height: 13, animation: 'spin 1s linear infinite' }} /> : <Plug style={{ width: 13, height: 13 }} />}
          {running ? 'Testing…' : 'Test'}
        </button>
      </div>
      {!hideUrlField && !result && !error && (
        <div style={{ fontSize: 11, color: '#6b7280' }}>
          The test obtains the auth for real (OAuth exchanges a token) and, with a URL, sends one GET with it. Secrets are never shown.
        </div>
      )}
      {error && <div role="alert" style={{ fontSize: 12, color: '#b91c1c' }}>{error}</div>}
      {result && (
        <div
          role="status"
          style={{
            border: `1px solid ${result.ok ? '#bbf7d0' : '#fecaca'}`, backgroundColor: result.ok ? '#f0fdf4' : '#fef2f2',
            borderRadius: 6, padding: '8px 10px', fontSize: 12,
          }}
        >
          <div style={{ fontWeight: 600, color: result.ok ? '#166534' : '#991b1b', marginBottom: 4 }}>
            {summarizeTest(result)}
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {result.steps.map((s, i) => (
              <li key={i} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', color: '#374151' }}>
                {s.ok
                  ? <CheckCircle style={{ width: 13, height: 13, color: '#16a34a', flexShrink: 0, marginTop: 1 }} />
                  : <XCircle style={{ width: 13, height: 13, color: '#dc2626', flexShrink: 0, marginTop: 1 }} />}
                <span><strong style={{ fontWeight: 600 }}>{s.step}:</strong> <span style={{ wordBreak: 'break-word' }}>{s.detail}</span></span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
