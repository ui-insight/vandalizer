import { useWorkspace } from '../../contexts/WorkspaceContext'

/** Keep known file caveats beside the tool, including when Files is collapsed. */
export function InputReadinessNotice() {
  const { selectedDocUuids, documentReadiness = {}, viewDocument } = useWorkspace()
  const affected = selectedDocUuids.map(uuid => documentReadiness[uuid]).filter(doc => doc?.message)
  if (!affected.length) return null
  return <section aria-label="Selected document readiness" style={{ flexShrink: 0, maxHeight: '25dvh', overflowY: 'auto', padding: '8px 12px', background: '#fffbeb', borderBottom: '1px solid #fcd34d', color: '#78350f', fontSize: 12, lineHeight: 1.45 }}>
    <details>
    <summary style={{ cursor: 'pointer', minHeight: 24 }}><strong>{affected.length} selected input{affected.length === 1 ? '' : 's'} need{affected.length === 1 ? 's' : ''} attention before use</strong></summary>
    <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
      {affected.map(doc => <li key={doc.uuid} style={{ overflowWrap: 'anywhere', marginBottom: 4 }}>
        <strong>{doc.title}:</strong> {doc.message}{' '}
        <button type="button" aria-label={`Inspect input: ${doc.title}`} onClick={() => viewDocument(doc.uuid, doc.title, undefined, { preserveChatScope: true })} style={{ color: 'inherit', textDecoration: 'underline', minHeight: 24 }}>Inspect file</button>
      </li>)}
    </ul>
    </details>
  </section>
}
