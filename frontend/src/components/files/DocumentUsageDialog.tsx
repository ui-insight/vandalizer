import { useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, Library, ListChecks, Workflow as WorkflowIcon, Folder, Loader2, ChevronRight } from 'lucide-react'
import { fetchDocumentUsage, type DocumentUsage } from '../../api/files'

/**
 * "Where is this used?" — every knowledge base, extraction and workflow that
 * references a document, plus its folder. A document could be removed without
 * any idea of what depended on it; this is the view that answers that, and
 * the delete confirmation shows the same list.
 */
interface DocumentUsageDialogProps {
  docUuid: string
  docTitle: string
  onClose: () => void
  onOpenWorkflow?: (id: string) => void
  onOpenExtraction?: (uuid: string) => void
  onOpenKnowledgeBase?: (uuid: string, title: string) => void
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** The reference sections of a usage payload — one document's, or several merged. */
export type UsageGroups = Pick<DocumentUsage, 'knowledge_bases' | 'extractions' | 'workflows' | 'total'>

/**
 * Merge usage across several documents (bulk delete) into one set of
 * references, de-duplicated by id: a knowledge base that holds three of the
 * selected files is one knowledge base, with its test cases / uses combined.
 */
export function mergeUsage(usages: DocumentUsage[]): UsageGroups {
  const kbs = new Map<string, DocumentUsage['knowledge_bases'][number]>()
  const exts = new Map<string, DocumentUsage['extractions'][number]>()
  const wfs = new Map<string, DocumentUsage['workflows'][number]>()
  for (const u of usages) {
    for (const kb of u.knowledge_bases) kbs.set(kb.uuid, kb)
    for (const ex of u.extractions) {
      const prev = exts.get(ex.uuid)
      if (!prev) { exts.set(ex.uuid, ex); continue }
      const seen = new Set(prev.test_cases.map(tc => tc.uuid))
      exts.set(ex.uuid, { ...prev, test_cases: [...prev.test_cases, ...ex.test_cases.filter(tc => !seen.has(tc.uuid))] })
    }
    for (const wf of u.workflows) {
      const prev = wfs.get(wf.id)
      if (!prev) { wfs.set(wf.id, wf); continue }
      const seen = new Set(prev.uses.map(use => JSON.stringify(use)))
      wfs.set(wf.id, { ...prev, uses: [...prev.uses, ...wf.uses.filter(use => !seen.has(JSON.stringify(use)))] })
    }
  }
  const knowledge_bases = [...kbs.values()]
  const extractions = [...exts.values()]
  const workflows = [...wfs.values()]
  return { knowledge_bases, extractions, workflows, total: knowledge_bases.length + extractions.length + workflows.length }
}

/** One sentence: "used in 1 knowledge base, 2 extractions and 1 workflow". */
export function summarizeUsage(usage: Pick<DocumentUsage, 'knowledge_bases' | 'extractions' | 'workflows'>): string {
  const parts: string[] = []
  if (usage.knowledge_bases.length) parts.push(plural(usage.knowledge_bases.length, 'knowledge base', 'knowledge bases'))
  if (usage.extractions.length) parts.push(plural(usage.extractions.length, 'extraction', 'extractions'))
  if (usage.workflows.length) parts.push(plural(usage.workflows.length, 'workflow', 'workflows'))
  if (parts.length === 0) return 'not used in any knowledge base, extraction or workflow'
  if (parts.length === 1) return `used in ${parts[0]}`
  return `used in ${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

export function describeWorkflowUse(use: DocumentUsage['workflows'][number]['uses'][number]): string {
  if (use.kind === 'fixed_document') return 'fixed document (Input tab)'
  const role = use.role || 'selected document'
  return use.step ? `${role} in step "${use.step}"` : role
}

/**
 * Shown in a delete confirmation when the usage lookup failed. Saying nothing
 * would read as "nothing depends on it", which is the one thing we do not know.
 */
export function UsageCheckFailedNote({ many = false }: { many?: boolean }) {
  return (
    <div role="status" style={{ marginTop: 8, fontSize: 12, color: '#b45309' }}>
      Couldn&apos;t check where {many ? 'these files are' : 'this document is'} used — {many ? 'they' : 'it'} may be a knowledge-base source, an extraction test case, or a workflow document.
    </div>
  )
}

/** Compact list of what references the document — reused inside the delete confirmation. */
export function UsageSummaryList({ usage }: { usage: Pick<DocumentUsage, 'knowledge_bases' | 'extractions' | 'workflows'> }) {
  const rows: { icon: typeof Library; label: string; detail?: string }[] = [
    ...usage.knowledge_bases.map(kb => ({ icon: Library, label: kb.title, detail: 'knowledge base' })),
    ...usage.extractions.map(ex => ({
      icon: ListChecks, label: ex.title,
      detail: `extraction · ${plural(ex.test_cases.length, 'test case', 'test cases')}`,
    })),
    ...usage.workflows.map(wf => ({
      icon: WorkflowIcon, label: wf.name,
      detail: `workflow · ${wf.uses.map(describeWorkflowUse).join(', ')}`,
    })),
  ]
  if (rows.length === 0) return null
  return (
    <ul style={{ listStyle: 'none', margin: '8px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {rows.map((r, i) => (
        <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, fontSize: 13 }}>
          <r.icon style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0, marginTop: 2 }} />
          <span>
            <strong style={{ fontWeight: 600 }}>{r.label}</strong>
            {r.detail && <span style={{ color: '#6b7280' }}> — {r.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Section({ icon: Icon, title, count, children }: {
  icon: typeof Library; title: string; count: number; children: React.ReactNode
}) {
  return (
    <section aria-label={title} style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        <Icon style={{ width: 13, height: 13 }} />
        {title}
        <span style={{ fontWeight: 500, textTransform: 'none', letterSpacing: 0 }}>({count})</span>
      </div>
      {count === 0 ? (
        <div style={{ fontSize: 13, color: '#9ca3af', paddingLeft: 19 }}>None</div>
      ) : children}
    </section>
  )
}

const linkStyle: React.CSSProperties = {
  background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit',
  fontSize: 13, fontWeight: 600, color: '#1d4ed8', textAlign: 'left',
}

export function DocumentUsageDialog({
  docUuid, docTitle, onClose, onOpenWorkflow, onOpenExtraction, onOpenKnowledgeBase,
}: DocumentUsageDialogProps) {
  const [usage, setUsage] = useState<DocumentUsage | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setUsage(null)
    setError(null)
    fetchDocumentUsage(docUuid)
      .then(u => { if (!cancelled) setUsage(u) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load where this document is used') })
    return () => { cancelled = true }
  }, [docUuid])

  const go = (fn?: () => void) => () => { if (fn) { fn(); onClose() } }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 700 }}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div
          className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="document-usage-title"
          style={{ maxHeight: '80vh', overflowY: 'auto' }}
        >
          <div className="mb-4 flex items-start justify-between" style={{ gap: 12 }}>
            <div>
              <h3 id="document-usage-title" className="text-lg font-medium text-gray-900">Where is this used?</h3>
              <div style={{ fontSize: 13, color: '#6b7280', wordBreak: 'break-word' }}>{docTitle}</div>
            </div>
            <button onClick={onClose} aria-label="Close dialog" className="text-gray-500 hover:text-gray-600" style={{ flexShrink: 0 }}>
              <X className="h-5 w-5" />
            </button>
          </div>

          {error && <div role="alert" style={{ fontSize: 13, color: '#b91c1c' }}>{error}</div>}
          {!usage && !error && (
            <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#6b7280' }}>
              <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite' }} /> Looking up references…
            </div>
          )}

          {usage && (
            <>
              <div style={{
                fontSize: 13, color: usage.total === 0 ? '#374151' : '#92400e',
                backgroundColor: usage.total === 0 ? '#f9fafb' : '#fffbeb',
                border: `1px solid ${usage.total === 0 ? '#e5e7eb' : '#fde68a'}`,
                borderRadius: 6, padding: '8px 12px', marginBottom: 16,
              }}>
                This document is {summarizeUsage(usage)}.
                {usage.total === 0
                  ? ' Deleting it will not affect anything else.'
                  : ' Deleting it will remove it from each of these; workflows that pin it will fail until it is replaced.'}
              </div>

              <Section icon={Folder} title="Location" count={1}>
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2, fontSize: 13, color: '#374151', paddingLeft: 19 }}>
                  <span>{usage.folder.team_id ? 'Team files' : 'My files'}</span>
                  {usage.folder.path.map(f => (
                    <span key={f.uuid} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                      <ChevronRight style={{ width: 12, height: 12, color: '#9ca3af' }} />
                      {f.title}
                    </span>
                  ))}
                </div>
              </Section>

              <Section icon={Library} title="Knowledge bases" count={usage.knowledge_bases.length}>
                <ul style={{ listStyle: 'none', margin: 0, padding: '0 0 0 19px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {usage.knowledge_bases.map(kb => (
                    <li key={kb.uuid}>
                      {onOpenKnowledgeBase && kb.exists
                        ? <button type="button" style={linkStyle} onClick={go(() => onOpenKnowledgeBase(kb.uuid, kb.title))}>{kb.title}</button>
                        : <span style={{ fontSize: 13, fontWeight: 600 }}>{kb.title}</span>}
                      <span style={{ fontSize: 12, color: '#6b7280' }}> — source</span>
                    </li>
                  ))}
                </ul>
              </Section>

              <Section icon={ListChecks} title="Extractions" count={usage.extractions.length}>
                <ul style={{ listStyle: 'none', margin: 0, padding: '0 0 0 19px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {usage.extractions.map(ex => (
                    <li key={ex.uuid}>
                      {onOpenExtraction && ex.exists
                        ? <button type="button" style={linkStyle} onClick={go(() => onOpenExtraction(ex.uuid))}>{ex.title}</button>
                        : <span style={{ fontSize: 13, fontWeight: 600 }}>{ex.title}</span>}
                      <span style={{ fontSize: 12, color: '#6b7280' }}>
                        {' — '}{plural(ex.test_cases.length, 'test case', 'test cases')}: {ex.test_cases.map(tc => tc.label).join(', ')}
                      </span>
                    </li>
                  ))}
                </ul>
              </Section>

              <Section icon={WorkflowIcon} title="Workflows" count={usage.workflows.length}>
                <ul style={{ listStyle: 'none', margin: 0, padding: '0 0 0 19px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {usage.workflows.map(wf => (
                    <li key={wf.id}>
                      {onOpenWorkflow
                        ? <button type="button" style={linkStyle} onClick={go(() => onOpenWorkflow(wf.id))}>{wf.name}</button>
                        : <span style={{ fontSize: 13, fontWeight: 600 }}>{wf.name}</span>}
                      <span style={{ fontSize: 12, color: '#6b7280' }}> — {wf.uses.map(describeWorkflowUse).join('; ')}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            </>
          )}

          <div className="mt-2 flex justify-end">
            <button type="button" onClick={onClose} className="rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100">
              Close
            </button>
          </div>
        </div>
      </FocusTrap>
    </div>
  )
}
