import { useEffect, useState } from 'react'
import { Check, X } from 'lucide-react'
import { getExtractionQualityRunResults, type QualityRunDocumentResult, type QualityRunFieldResult } from '../../api/extractions'

/** What a field's result was: every replicate matched, some did, or none. */
function outcome(f: QualityRunFieldResult): { text: string; color: string; matched: boolean | null } {
  if (f.accuracy == null) return { text: 'Not scored', color: '#6b7280', matched: null }
  if (f.accuracy >= 1) return { text: 'Matched', color: '#15803d', matched: true }
  if (f.accuracy <= 0) return { text: 'Missed', color: '#dc2626', matched: false }
  return { text: `Matched ${Math.round(f.accuracy * 100)}% of runs`, color: '#92400e', matched: false }
}

const cell: React.CSSProperties = { padding: 'var(--workspace-space-2) var(--workspace-space-6)', verticalAlign: 'top', textAlign: 'left' }
const empty = <span style={{ color: '#9ca3af' }}>(empty)</span>

/**
 * A Quality History run's per-field results — which fields matched the
 * expected value and which missed — loaded when the run is expanded.
 */
export function QualityRunResults({ searchSetUuid, runUuid }: { searchSetUuid: string; runUuid: string }) {
  const [documents, setDocuments] = useState<QualityRunDocumentResult[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    getExtractionQualityRunResults(searchSetUuid, runUuid)
      .then(res => { if (!cancelled) setDocuments(res.documents) })
      .catch(() => { if (!cancelled) setError(true) })
    return () => { cancelled = true }
  }, [searchSetUuid, runUuid])

  if (error) return <p role="alert" style={{ color: '#dc2626', margin: 0 }}>Could not load this run's field results.</p>
  if (!documents) return <p style={{ color: '#6b7280', margin: 0 }}>Loading field results…</p>
  if (documents.length === 0) return <p style={{ color: '#6b7280', margin: 0 }}>This run saved no per-field results.</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
      {documents.map((doc, i) => (
        <table key={doc.test_case_uuid || i} style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--workspace-font-meta)' }}>
          <caption style={{ textAlign: 'left', fontWeight: 600, color: '#4b5563', paddingBottom: 'var(--workspace-space-2)' }}>
            {doc.label || `Document ${i + 1}`}
          </caption>
          <thead>
            <tr style={{ color: '#6b7280' }}>
              <th style={{ ...cell, fontWeight: 500 }}>Field</th>
              <th style={{ ...cell, fontWeight: 500 }}>Expected</th>
              <th style={{ ...cell, fontWeight: 500 }}>Extracted</th>
              <th style={{ ...cell, fontWeight: 500 }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {doc.fields.map(f => {
              const o = outcome(f)
              return (
                <tr key={f.field_name} style={{ borderTop: '1px solid #f3f4f6' }}>
                  <td style={{ ...cell, color: '#374151', fontWeight: 500 }}>{f.field_name}</td>
                  <td style={{ ...cell, color: '#374151' }}>{f.expected || empty}</td>
                  <td style={{ ...cell, color: '#374151' }}>{f.most_common_value || empty}</td>
                  <td style={{ ...cell, color: o.color, whiteSpace: 'nowrap' }}>
                    {o.matched === true && <Check aria-hidden="true" style={{ width: 11, height: 11, marginRight: 2, verticalAlign: '-1px' }} />}
                    {o.matched === false && <X aria-hidden="true" style={{ width: 11, height: 11, marginRight: 2, verticalAlign: '-1px' }} />}
                    {o.text}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      ))}
    </div>
  )
}
