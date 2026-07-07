import { useCallback, useEffect, useState } from 'react'
import { BarChart3, X } from 'lucide-react'

import { getTelemetryOptIn, setTelemetryOptIn } from '../../api/admin'

/**
 * One-time opt-in prompt for anonymous usage telemetry, shown to global admins
 * on the Admin page when the deployment has never made a telemetry decision and
 * the installer never asked. Dismissing or choosing either option records the
 * decision server-side, so it does not reappear.
 */
export function TelemetryOptInBanner() {
  const [show, setShow] = useState(false)
  const [org, setOrg] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTelemetryOptIn()
      .then(s => setShow(s.show_banner))
      .catch(() => {})
  }, [])

  const decide = useCallback(async (enabled: boolean) => {
    setBusy(true)
    setError(null)
    try {
      await setTelemetryOptIn({ enabled, organization: enabled ? org.trim() : undefined })
      setShow(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your choice')
      setBusy(false)
    }
  }, [org])

  if (!show) return null

  return (
    <div style={{
      border: '1px solid #c7d2fe', backgroundColor: '#eef2ff', borderRadius: 10,
      padding: '14px 16px', marginBottom: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <BarChart3 size={18} color="#4f46e5" style={{ marginTop: 2, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#312e81' }}>
            Help improve Vandalizer with anonymous usage stats?
          </div>
          <div style={{ fontSize: 13, color: '#4338ca', marginTop: 4, lineHeight: 1.5 }}>
            A once-a-day heartbeat sends only an anonymous ID, the version, and coarse
            usage buckets (e.g. "11–50 users"). Never documents, names, emails, or keys.{' '}
            <a href="https://github.com/ui-insight/vandalizer/blob/main/docs/telemetry.md"
               target="_blank" rel="noreferrer"
               style={{ color: '#4f46e5', fontWeight: 500 }}>
              What's collected
            </a>
          </div>

          <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <input
              type="text"
              value={org}
              onChange={e => setOrg(e.target.value)}
              placeholder="Optional: your organization (blank = anonymous)"
              disabled={busy}
              style={{
                flex: '1 1 260px', minWidth: 200,
                padding: '6px 10px', fontSize: 13,
                border: '1px solid #c7d2fe', borderRadius: 6, backgroundColor: '#fff',
              }}
            />
            <button
              onClick={() => void decide(true)}
              disabled={busy}
              style={{
                padding: '7px 14px', fontSize: 13, fontWeight: 600,
                backgroundColor: '#4f46e5', color: '#fff',
                border: 'none', borderRadius: 6, cursor: busy ? 'default' : 'pointer',
              }}
            >
              Enable telemetry
            </button>
            <button
              onClick={() => void decide(false)}
              disabled={busy}
              style={{
                padding: '7px 14px', fontSize: 13, fontWeight: 500,
                backgroundColor: 'transparent', color: '#4338ca',
                border: '1px solid #c7d2fe', borderRadius: 6, cursor: busy ? 'default' : 'pointer',
              }}
            >
              No thanks
            </button>
          </div>
          {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 8 }}>{error}</div>}
        </div>

        <button
          onClick={() => void decide(false)}
          disabled={busy}
          title="Dismiss (declines telemetry)"
          style={{
            background: 'none', border: 'none', cursor: busy ? 'default' : 'pointer',
            color: '#6366f1', padding: 2, flexShrink: 0,
          }}
        >
          <X size={16} />
        </button>
      </div>
    </div>
  )
}
