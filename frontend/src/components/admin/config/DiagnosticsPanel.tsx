import { useState } from 'react'
import { CheckCircle2, XCircle, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'

// ──────────────────────────────────────────
// Shared connectivity diagnostics
// ──────────────────────────────────────────

// The step-by-step result of a "Test" button: on success, why the hook-up is
// healthy (the facts row, plus whatever came back); on failure, a classified
// error with a plain-English cause and a suggested fix.
//
// Shared between the model test and the OCR test because both answer the same
// question — "is this thing actually doing its job?" — and an admin should not
// have to learn two layouts to read the answer.

export type DiagnosticCheck = { label: string; ok: boolean; detail: string }

export type DiagnosticError = {
  category: string
  title: string
  why: string
  fix: string
  raw: string
}

export type DiagnosticFact = { label: string; value: string; mono?: boolean }

export function DiagnosticsPanel({
  ok,
  summary,
  checks,
  facts = [],
  preview,
  previewLabel = 'reply',
  error,
  rawLabel = 'raw provider error',
}: {
  ok: boolean
  summary: string
  checks: DiagnosticCheck[]
  facts?: DiagnosticFact[]
  preview?: string
  previewLabel?: string
  error?: DiagnosticError | null
  rawLabel?: string
}) {
  const [showRaw, setShowRaw] = useState(false)
  const accent = ok ? '#16a34a' : '#dc2626'
  return (
    <div style={{
      padding: '12px 16px', fontSize: 13,
      background: ok ? '#f0fdf4' : '#fef2f2',
      border: '1px solid', borderTop: 'none',
      borderColor: ok ? '#bbf7d0' : '#fecaca',
      borderRadius: '0 0 var(--ui-radius, 12px) var(--ui-radius, 12px)',
    }}>
      <div style={{ fontWeight: 600, color: ok ? '#166534' : '#991b1b', marginBottom: 10 }}>
        {summary}
      </div>

      {/* Step-by-step checks */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {checks.map((c, idx) => (
          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            {c.ok
              ? <CheckCircle2 size={15} style={{ color: '#16a34a', flexShrink: 0, marginTop: 1 }} />
              : <XCircle size={15} style={{ color: '#dc2626', flexShrink: 0, marginTop: 1 }} />}
            <span style={{ color: '#374151' }}>
              <span style={{ fontWeight: 600 }}>{c.label}:</span> {c.detail}
            </span>
          </div>
        ))}
      </div>

      {/* Success facts */}
      {ok && facts.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          {facts.map((f, idx) => <DiagFact key={idx} label={f.label} value={f.value} mono={f.mono} />)}
        </div>
      )}
      {ok && preview && (
        <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff', border: '1px solid #d1fae5', borderRadius: 8, fontFamily: 'ui-monospace, monospace', fontSize: 12, color: '#374151' }}>
          <span style={{ color: '#9ca3af' }}>{previewLabel}:</span> {preview}
        </div>
      )}

      {/* Failure guidance */}
      {!ok && error && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <AlertCircle size={15} style={{ color: accent, flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontWeight: 600, color: '#991b1b' }}>{error.title}</div>
              <div style={{ color: '#374151', marginTop: 2 }}>{error.why}</div>
            </div>
          </div>
          <div style={{ padding: '8px 10px', background: '#fff', border: '1px solid #fecaca', borderRadius: 8, color: '#374151' }}>
            <span style={{ fontWeight: 600, color: '#b91c1c' }}>Try this: </span>{error.fix}
          </div>
          {error.raw && (
            <div>
              <button
                onClick={() => setShowRaw(v => !v)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: 12, padding: 0, display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                {showRaw ? <ChevronUp size={12} /> : <ChevronDown size={12} />} {showRaw ? 'Hide' : 'Show'} {rawLabel}
              </button>
              {showRaw && (
                <pre style={{ marginTop: 6, padding: '8px 10px', background: '#1f2937', color: '#f9fafb', borderRadius: 8, fontSize: 11, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {error.raw}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function DiagFact({ label, value, mono }: DiagnosticFact) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 9999, fontSize: 12 }}>
      <span style={{ color: '#9ca3af', fontWeight: 600 }}>{label}</span>
      <span style={{ color: '#374151', fontFamily: mono ? 'ui-monospace, monospace' : undefined }}>{value}</span>
    </span>
  )
}
