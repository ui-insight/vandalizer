import { useState } from 'react'
import type { ReactNode } from 'react'
import { Check, ChevronRight, ClipboardCopy, Download, ExternalLink, FileText, Loader2 } from 'lucide-react'
import { QualityBadge } from './QualityBadge'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import type { WorkspaceMode } from '../../contexts/WorkspaceContext'
import type { ToolCallInfo, ToolResultInfo, QualityMeta } from '../../types/chat'

// ---------------------------------------------------------------------------
// Tool metadata
// ---------------------------------------------------------------------------

type ToolCategory = 'read' | 'extract' | 'write' | 'workflow'

const TOOL_META: Record<string, { label: string; category: ToolCategory }> = {
  search_documents:      { label: 'Searching documents',      category: 'read' },
  list_documents:        { label: 'Listing documents',        category: 'read' },
  search_knowledge_base: { label: 'Querying knowledge base',  category: 'read' },
  list_knowledge_bases:  { label: 'Listing knowledge bases',  category: 'read' },
  list_extraction_sets:  { label: 'Listing extraction templates',  category: 'read' },
  list_workflows:        { label: 'Listing workflows',        category: 'read' },
  get_quality_info:      { label: 'Checking quality',         category: 'read' },
  search_library:        { label: 'Searching library',        category: 'read' },
  get_document_text:     { label: 'Reading document',         category: 'read' },
  run_extraction:        { label: 'Running extraction',       category: 'extract' },
  create_knowledge_base: { label: 'Creating knowledge base',  category: 'write' },
  add_documents_to_kb:   { label: 'Adding documents to KB',   category: 'write' },
  add_url_to_kb:         { label: 'Adding URL to KB',         category: 'write' },
  run_workflow:          { label: 'Running workflow',          category: 'workflow' },
  get_workflow_status:   { label: 'Checking workflow status',  category: 'workflow' },
  list_test_cases:       { label: 'Listing test cases',         category: 'read' },
  propose_test_case:     { label: 'Preparing guided verification', category: 'extract' },
  run_validation:        { label: 'Running validation',         category: 'workflow' },
  create_extraction_from_document: { label: 'Building extraction from document', category: 'write' },
}

const CATEGORY_ACCENT: Record<ToolCategory, string> = {
  read: '#3b82f6',
  extract: '#f59e0b',
  write: '#22c55e',
  workflow: '#8b5cf6',
}

function getMeta(name: string) {
  return TOOL_META[name] || { label: name.replace(/_/g, ' '), category: 'read' as ToolCategory }
}

// ---------------------------------------------------------------------------
// Context hints for ACTIVE (in-progress) tools
// ---------------------------------------------------------------------------

function getActiveHint(toolName: string, args: Record<string, unknown>): string {
  const q = args.query || args.search || args.title || args.url
  const queryStr = typeof q === 'string' ? (q.length > 50 ? q.slice(0, 47) + '...' : q) : ''

  switch (toolName) {
    case 'search_library':
    case 'search_documents':
    case 'list_extraction_sets':
    case 'list_workflows':
    case 'list_knowledge_bases':
      return queryStr ? `for "${queryStr}"` : ''
    case 'search_knowledge_base':
      return queryStr ? `about "${queryStr}"` : ''
    case 'run_extraction': {
      const docs = Array.isArray(args.document_uuids) ? args.document_uuids.length : 0
      return docs > 0 ? `on ${docs} document${docs !== 1 ? 's' : ''}` : ''
    }
    case 'create_extraction_from_document': {
      const docs = Array.isArray(args.document_uuids) ? args.document_uuids.length : 0
      return docs > 0 ? `from ${docs} document${docs !== 1 ? 's' : ''}` : ''
    }
    case 'get_document_text':
      return ''
    default:
      return queryStr
  }
}

// ---------------------------------------------------------------------------
// Rich result summaries — pulls names, counts, and quality naturally
// ---------------------------------------------------------------------------

interface ResultSummary {
  /** Main description — e.g. 'Found "NSF Grant Proposal" template' */
  text: string
  /** Quality/accuracy annotation — e.g. '92% accuracy · 847 validations' */
  qualityHint: string
}

function summarizeResult(toolName: string, content: unknown, quality: QualityMeta | null): ResultSummary {
  const empty: ResultSummary = { text: '', qualityHint: '' }
  if (content == null) return empty
  const obj = content as Record<string, unknown>

  if (obj.error) return { text: String(obj.error), qualityHint: '' }
  if (obj.needs_confirmation) return { text: obj.preview ? String(obj.preview) : 'Awaiting confirmation', qualityHint: '' }

  // Build quality hint from sidecar
  const qualityHint = formatQualityHint(quality)

  switch (toolName) {
    case 'search_library': {
      if (!Array.isArray(content)) break
      if (content.length === 0) return { text: 'No matching templates found', qualityHint: '' }
      const first = content[0] as Record<string, unknown>
      const name = first.name ? `"${first.name}"` : ''
      const verified = first.verified ? ' (verified)' : ''
      if (content.length === 1) {
        return { text: `Found ${name}${verified}`, qualityHint }
      }
      return { text: `Found ${content.length} items — ${name}${verified}`, qualityHint }
    }

    case 'search_documents': {
      if (!Array.isArray(content)) break
      if (content.length === 0) return { text: 'No documents found', qualityHint: '' }
      const first = content[0] as Record<string, unknown>
      const title = first.title ? `"${String(first.title).slice(0, 40)}"` : ''
      if (content.length === 1) return { text: `Found ${title}`, qualityHint }
      return { text: `Found ${content.length} documents — ${title}`, qualityHint }
    }

    case 'list_extraction_sets':
    case 'list_workflows':
    case 'list_knowledge_bases': {
      if (!Array.isArray(content)) break
      const type = toolName === 'list_extraction_sets' ? 'template' :
        toolName === 'list_workflows' ? 'workflow' : 'knowledge base'
      if (content.length === 0) return { text: `No ${type}s found`, qualityHint: '' }
      return { text: `Found ${content.length} ${type}${content.length !== 1 ? 's' : ''}`, qualityHint }
    }

    case 'list_documents': {
      const docs = Array.isArray(obj.documents) ? obj.documents.length : 0
      const folders = Array.isArray(obj.folders) ? obj.folders.length : 0
      const parts: string[] = []
      if (docs > 0) parts.push(`${docs} document${docs !== 1 ? 's' : ''}`)
      if (folders > 0) parts.push(`${folders} folder${folders !== 1 ? 's' : ''}`)
      return { text: parts.length > 0 ? parts.join(', ') : 'Empty folder', qualityHint }
    }

    case 'search_knowledge_base': {
      if (!Array.isArray(content)) break
      if (content.length === 0) return { text: 'No matching passages', qualityHint: '' }
      return { text: `Found ${content.length} relevant passage${content.length !== 1 ? 's' : ''}`, qualityHint }
    }

    case 'get_document_text': {
      const title = obj.title ? `"${String(obj.title).slice(0, 40)}"` : ''
      const chars = obj.total_chars ? `${((obj.total_chars as number) / 1000).toFixed(0)}K chars` : ''
      return { text: [title, chars].filter(Boolean).join(' — '), qualityHint }
    }

    case 'run_extraction': {
      const count = (obj.entity_count as number) || 0
      const fields = Array.isArray(obj.fields) ? obj.fields.length : 0
      const setName = obj.extraction_set ? `"${obj.extraction_set}"` : ''
      const fieldHint = fields > 0 ? `${fields} fields` : ''
      const entityHint = `${count} entit${count !== 1 ? 'ies' : 'y'}`
      const parts = [entityHint, fieldHint].filter(Boolean).join(', ')
      return {
        text: setName ? `${setName} — ${parts}` : parts,
        qualityHint,
      }
    }

    case 'propose_test_case': {
      const count = Array.isArray(obj.fields) ? (obj.fields as unknown[]).length : 0
      const title = obj.document_title ? `"${String(obj.document_title).slice(0, 40)}"` : ''
      return {
        text: `${title} — ${count} field${count !== 1 ? 's' : ''} ready to verify`,
        qualityHint: '',
      }
    }

    case 'run_validation': {
      if (obj.score != null) {
        const tc = obj.num_test_cases || 0
        return {
          text: `Score: ${Math.round(obj.score as number)}/100 · ${tc} test case${tc !== 1 ? 's' : ''}`,
          qualityHint,
        }
      }
      return { text: 'Validation complete', qualityHint: '' }
    }

    case 'list_test_cases': {
      const count = (obj.count as number) || 0
      const setName = obj.extraction_set ? `"${obj.extraction_set}"` : ''
      return { text: `${setName} — ${count} test case${count !== 1 ? 's' : ''}`, qualityHint: '' }
    }

    case 'create_extraction_from_document': {
      const fields = Array.isArray(obj.fields) ? (obj.fields as unknown[]).length : 0
      const title = obj.title ? `"${String(obj.title).slice(0, 40)}"` : ''
      if (fields > 0) {
        return { text: `${title} — ${fields} field${fields !== 1 ? 's' : ''} discovered`, qualityHint: '' }
      }
      return { text: obj.message ? String(obj.message) : 'Created', qualityHint: '' }
    }

    case 'get_quality_info':
      if (obj.score != null) return { text: `Score: ${Math.round(obj.score as number)}/100`, qualityHint }
      return { text: obj.note ? String(obj.note) : 'No validation data', qualityHint: '' }

    case 'create_knowledge_base':
    case 'add_documents_to_kb':
    case 'add_url_to_kb':
      return { text: obj.message ? String(obj.message) : 'Done', qualityHint }

    case 'run_workflow':
      return { text: 'Started', qualityHint }

    case 'get_workflow_status': {
      const status = obj.status as string
      if (status === 'completed') return { text: 'Completed', qualityHint }
      if (status === 'paused') return { text: 'Paused — awaiting approval', qualityHint: '' }
      if (status === 'failed') return { text: 'Failed', qualityHint: '' }
      const done = (obj.steps_completed as number) || 0
      const total = (obj.steps_total as number) || 0
      return { text: `${done}/${total} steps`, qualityHint }
    }
  }

  // Generic fallback
  if (Array.isArray(content))
    return { text: content.length > 0 ? `${content.length} results` : 'No results', qualityHint }
  if (obj.message && typeof obj.message === 'string') return { text: String(obj.message), qualityHint }
  return { text: '', qualityHint }
}

function formatQualityHint(quality: QualityMeta | null): string {
  if (!quality) return ''
  const parts: string[] = []
  if (quality.accuracy != null) {
    parts.push(`${Math.round(quality.accuracy * 100)}% accuracy`)
  } else if (quality.score != null) {
    parts.push(`${Math.round(quality.score)}/100 quality`)
  }
  if (quality.num_runs != null && quality.num_runs > 0) {
    parts.push(`${quality.num_runs} validation${quality.num_runs !== 1 ? 's' : ''}`)
  } else if (quality.num_test_cases != null && quality.num_test_cases > 0) {
    parts.push(`${quality.num_test_cases} test case${quality.num_test_cases !== 1 ? 's' : ''}`)
  }
  return parts.join(' · ')
}

// ---------------------------------------------------------------------------
// Data export utilities
// ---------------------------------------------------------------------------

function csvEscape(val: unknown): string {
  const s = val == null ? '' : String(val)
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** Serialize a tool result's content to a human-readable clipboard string. */
export function toolResultToText(toolName: string, content: unknown): string {
  if (content == null) return ''
  const obj = content as Record<string, unknown>

  // Extraction: entities as tab-delimited table
  if (toolName === 'run_extraction' && Array.isArray(obj.entities)) {
    const entities = obj.entities as Array<Record<string, unknown>>
    const fields = (obj.fields as string[]) || (entities.length > 0 ? Object.keys(entities[0]) : [])
    if (fields.length === 0) return JSON.stringify(content, null, 2)
    const header = fields.join('\t')
    const rows = entities.map(e => fields.map(f => e[f] != null ? String(e[f]) : '').join('\t'))
    return [header, ...rows].join('\n')
  }

  // KB passages: source + content
  if (toolName === 'search_knowledge_base' && Array.isArray(content)) {
    return (content as Array<Record<string, unknown>>)
      .map(c => `[${c.source_name || 'Source'}]\n${c.content || ''}`)
      .join('\n\n')
  }

  // Lists: pull title/name
  if (Array.isArray(content)) {
    return (content as Array<Record<string, unknown>>)
      .map(item => String(item.title || item.name || item.uuid || JSON.stringify(item)))
      .join('\n')
  }

  // Workflow output
  if (toolName === 'get_workflow_status' && obj.output != null) {
    if (typeof obj.output === 'string') return obj.output
    return JSON.stringify(obj.output, null, 2)
  }

  // Document text
  if (toolName === 'get_document_text' && obj.text) return String(obj.text)

  // list_documents
  if (toolName === 'list_documents' && Array.isArray(obj.documents)) {
    return (obj.documents as Array<Record<string, unknown>>)
      .map(d => String(d.title || d.name || 'Untitled'))
      .join('\n')
  }

  // Fallback
  return typeof content === 'string' ? content : JSON.stringify(content, null, 2)
}

function extractionToCSV(content: Record<string, unknown>): string | null {
  const entities = content.entities as Array<Record<string, unknown>> | undefined
  if (!entities || entities.length === 0) return null
  const fields = (content.fields as string[]) || Object.keys(entities[0])
  if (fields.length === 0) return null
  const header = fields.map(csvEscape).join(',')
  const rows = entities.map(e => fields.map(f => csvEscape(e[f])).join(','))
  return [header, ...rows].join('\n')
}

/** Check whether a tool result has meaningful copyable data. */
function hasCopyableContent(toolName: string, content: unknown): boolean {
  if (content == null) return false
  const obj = content as Record<string, unknown>
  if (obj.error || obj.needs_confirmation) return false
  if (toolName === 'run_extraction') return Array.isArray(obj.entities) && obj.entities.length > 0
  if (toolName === 'search_knowledge_base') return Array.isArray(content) && content.length > 0
  if (toolName === 'get_workflow_status') return obj.status === 'completed' && obj.output != null
  if (toolName === 'get_document_text') return Boolean(obj.text)
  if (toolName === 'list_documents') return Array.isArray(obj.documents) && obj.documents.length > 0
  if (Array.isArray(content)) return content.length > 0
  return false
}

/** Does this tool result render a rich content block that has its own copy/export buttons? */
function hasRichContent(toolName: string, obj: Record<string, unknown> | undefined): boolean {
  if (!obj) return false
  if (toolName === 'run_extraction' && obj.entities != null) return true
  if (toolName === 'search_knowledge_base') return true
  if (toolName === 'get_workflow_status' && obj.status === 'completed' && obj.output != null) return true
  return false
}

/** Small inline copy button with checkmark feedback. */
function CopyButton({ text, label = 'Copy data' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      title={label}
      aria-label={label}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 20, height: 20, borderRadius: 4, border: 'none',
        background: 'transparent', cursor: 'pointer',
        color: copied ? '#16a34a' : '#c4c9d1',
        transition: 'color 0.15s',
        flexShrink: 0,
      }}
    >
      {copied ? <Check size={11} /> : <ClipboardCopy size={11} />}
    </button>
  )
}

/** Small inline CSV download button. */
function CSVDownloadButton({ csv, filename }: { csv: string; filename: string }) {
  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    downloadBlob(new Blob([csv], { type: 'text/csv' }), filename)
  }
  return (
    <button
      onClick={handleDownload}
      title="Download CSV"
      aria-label="Download CSV"
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 20, height: 20, borderRadius: 4, border: 'none',
        background: 'transparent', cursor: 'pointer',
        color: '#c4c9d1', transition: 'color 0.15s',
        flexShrink: 0,
      }}
    >
      <Download size={11} />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Auto-shown rich content
// ---------------------------------------------------------------------------

/** Key-value pairs for single-entity extractions, compact table for multi. */
function ExtractionContent({ content }: { content: Record<string, unknown> }) {
  const [showAll, setShowAll] = useState(false)
  const entities = content.entities as Array<Record<string, unknown>> | undefined
  if (!entities || entities.length === 0) return null
  const fields = (content.fields as string[]) || Object.keys(entities[0])
  if (fields.length === 0) return null

  const copyText = toolResultToText('run_extraction', content)
  const csv = extractionToCSV(content)
  const setName = content.extraction_set ? String(content.extraction_set).replace(/\s+/g, '_') : 'extraction'

  // Single entity: key-value pairs
  if (entities.length === 1) {
    const entity = entities[0]
    const entries = fields
      .filter((f) => entity[f] != null && String(entity[f]).trim() !== '' && String(entity[f]) !== '--')
    const visibleLimit = showAll ? entries.length : 8
    const shown = entries.slice(0, visibleLimit)
    const remaining = entries.length - shown.length

    return (
      <div style={{ marginTop: 4, marginLeft: 20, fontSize: 12, lineHeight: 1.7 }}>
        {shown.map((f) => (
          <div key={f} style={{ display: 'flex', gap: 8 }}>
            <span style={{ color: '#9ca3af', minWidth: 140, flexShrink: 0 }}>{f}</span>
            <span style={{ color: '#374151' }}>
              {String(entity[f]).length > 80
                ? String(entity[f]).slice(0, 77) + '...'
                : String(entity[f])}
            </span>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
          {remaining > 0 && (
            <button
              onClick={() => setShowAll(true)}
              style={{
                background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                color: '#3b82f6', fontSize: 11,
              }}
            >
              +{remaining} more fields
            </button>
          )}
          {showAll && entries.length > 8 && (
            <button
              onClick={() => setShowAll(false)}
              style={{
                background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                color: '#3b82f6', fontSize: 11,
              }}
            >
              Show less
            </button>
          )}
          <span style={{ flex: 1 }} />
          <CopyButton text={copyText} label="Copy extraction data" />
          {csv && <CSVDownloadButton csv={csv} filename={`${setName}.csv`} />}
        </div>
      </div>
    )
  }

  // Multiple entities: compact table with limited columns
  const maxCols = showAll ? fields.length : 6
  const maxRows = showAll ? entities.length : 12
  const visibleFields = fields.slice(0, maxCols)
  const hiddenCols = fields.length - visibleFields.length
  const hiddenRows = entities.length - Math.min(entities.length, maxRows)

  return (
    <div style={{ overflowX: 'auto', marginTop: 4, marginLeft: 20 }}>
      <table style={{
        width: '100%', borderCollapse: 'collapse', fontSize: 11, lineHeight: 1.4,
      }}>
        <thead>
          <tr>
            {visibleFields.map((f) => (
              <th key={f} style={{
                textAlign: 'left', padding: '4px 8px', borderBottom: '2px solid #e5e7eb',
                fontWeight: 600, color: '#374151', whiteSpace: 'nowrap',
              }}>
                {f}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entities.slice(0, maxRows).map((entity, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
              {visibleFields.map((f) => (
                <td key={f} style={{
                  padding: '3px 8px', color: '#4b5563', maxWidth: 200,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {entity[f] != null ? String(entity[f]) : <span style={{ color: '#d1d5db' }}>--</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ color: '#c4c9d1', fontSize: 10, marginTop: 2, display: 'flex', alignItems: 'center', gap: 12 }}>
        {!showAll && (hiddenRows > 0 || hiddenCols > 0) && (
          <button
            onClick={() => setShowAll(true)}
            style={{
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              color: '#3b82f6', fontSize: 10,
            }}
          >
            {[hiddenRows > 0 && `+${hiddenRows} rows`, hiddenCols > 0 && `+${hiddenCols} cols`].filter(Boolean).join(', ')} — show all
          </button>
        )}
        {showAll && (entities.length > 12 || fields.length > 6) && (
          <button
            onClick={() => setShowAll(false)}
            style={{
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              color: '#3b82f6', fontSize: 10,
            }}
          >
            Show less
          </button>
        )}
        <span style={{ flex: 1 }} />
        <CopyButton text={copyText} label="Copy extraction data" />
        {csv && <CSVDownloadButton csv={csv} filename={`${setName}.csv`} />}
      </div>
    </div>
  )
}

/** Pick a short phrase from chunk content for PDF text-search highlighting. */
function pickHighlightPhrase(content: string): string {
  const cleaned = content.replace(/\s+/g, ' ').trim()
  if (cleaned.length <= 60) return cleaned
  const cut = cleaned.slice(0, 60)
  const lastSpace = cut.lastIndexOf(' ')
  return lastSpace > 20 ? cut.slice(0, lastSpace) : cut
}

interface KBSourceActions {
  viewDocument: (uuid: string, title: string) => void
  setHighlightTerms: (terms: string[]) => void
  setWorkspaceMode: (mode: WorkspaceMode) => void
}

function KBPassages({ content, actions }: { content: unknown; actions?: KBSourceActions }) {
  if (!Array.isArray(content) || content.length === 0) return null
  const passages = content as Array<Record<string, unknown>>
  const copyText = toolResultToText('search_knowledge_base', content)

  return (
    <div style={{ marginTop: 4, marginLeft: 20, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {passages.slice(0, 3).map((chunk, i) => {
        const sourceType = chunk.source_type as string | undefined
        const docUuid = chunk.document_uuid as string | undefined
        const url = chunk.url as string | undefined
        const sourceName = String(chunk.source_name || 'Source')
        const chunkContent = String(chunk.content || '')

        const isDoc = sourceType === 'document' && docUuid
        const isUrl = sourceType === 'url' && url
        const isClickable = actions && (isDoc || isUrl)

        const handleClick = () => {
          if (!actions) return
          if (isDoc) {
            actions.setWorkspaceMode('files')
            actions.viewDocument(docUuid, sourceName)
            actions.setHighlightTerms([pickHighlightPhrase(chunkContent)])
          } else if (isUrl) {
            window.open(url, '_blank', 'noopener,noreferrer')
          }
        }

        return (
          <div key={i} style={{
            fontSize: 11, lineHeight: 1.5, color: '#6b7280',
            padding: '4px 8px', borderLeft: '2px solid #e5e7eb',
            background: '#fafafa', borderRadius: '0 4px 4px 0',
          }}>
            <span
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onClick={isClickable ? handleClick : undefined}
              onKeyDown={isClickable ? (e) => { if (e.key === 'Enter') handleClick() } : undefined}
              style={{
                fontWeight: 500, fontSize: 10,
                color: isClickable ? '#3b82f6' : '#9ca3af',
                cursor: isClickable ? 'pointer' : 'default',
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}
            >
              {isDoc && <FileText size={10} style={{ flexShrink: 0 }} />}
              {isUrl && <ExternalLink size={9} style={{ flexShrink: 0 }} />}
              {sourceName}
            </span>
            <span style={{ margin: '0 6px', color: '#d1d5db' }}>&middot;</span>
            <span>{chunkContent.slice(0, 200)}{chunkContent.length > 200 ? '...' : ''}</span>
          </div>
        )
      })}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <CopyButton text={copyText} label="Copy passages" />
      </div>
    </div>
  )
}

/** Render completed workflow output as structured content. */
function WorkflowOutput({ content }: { content: Record<string, unknown> }) {
  const status = content.status as string | undefined
  if (status !== 'completed') return null

  const output = content.output
  if (output == null) return null

  const copyText = typeof output === 'string' ? output : JSON.stringify(output, null, 2)

  // If output is a string, show it as a block
  if (typeof output === 'string') {
    if (output.trim().length === 0) return null
    return (
      <div style={{ marginTop: 4, marginLeft: 20 }}>
        <div style={{
          fontSize: 12, lineHeight: 1.6,
          color: '#374151', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          maxHeight: 200, overflow: 'auto', padding: '8px 12px',
          background: '#fafafa', borderRadius: 6, border: '1px solid #f3f4f6',
        }}>
          {output.length > 1000 ? output.slice(0, 997) + '...' : output}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 2 }}>
          <CopyButton text={copyText} label="Copy workflow output" />
        </div>
      </div>
    )
  }

  // If output is an object with key-value data, render as pairs
  if (typeof output === 'object' && !Array.isArray(output)) {
    const entries = Object.entries(output as Record<string, unknown>)
      .filter(([, v]) => v != null && String(v).trim() !== '')
      .slice(0, 12)
    if (entries.length === 0) return null
    return (
      <div style={{ marginTop: 4, marginLeft: 20, fontSize: 12, lineHeight: 1.7 }}>
        {entries.map(([k, v]) => (
          <div key={k} style={{ display: 'flex', gap: 8 }}>
            <span style={{ color: '#9ca3af', minWidth: 140, flexShrink: 0 }}>{k}</span>
            <span style={{ color: '#374151' }}>
              {String(v).length > 80 ? String(v).slice(0, 77) + '...' : String(v)}
            </span>
          </div>
        ))}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 2 }}>
          <CopyButton text={copyText} label="Copy workflow output" />
        </div>
      </div>
    )
  }

  return null
}

interface VerificationLauncherActions {
  viewDocument: (uuid: string, title: string) => void
  setWorkspaceMode: (mode: WorkspaceMode) => void
  openVerification: (sessionId: string) => void
}

function VerificationLauncher({
  content,
  actions,
}: {
  content: Record<string, unknown>
  actions: VerificationLauncherActions
}) {
  const sessionId = content.verification_session_id as string | undefined
  const docUuid = content.document_uuid as string | undefined
  const docTitle = String(content.document_title || 'document')
  const fields = (content.fields as Array<Record<string, unknown>>) || []
  const label = String(content.label || '')

  if (!sessionId || !docUuid) return null

  const handleStart = () => {
    actions.setWorkspaceMode('files')
    actions.viewDocument(docUuid, docTitle)
    actions.openVerification(sessionId)
  }

  return (
    <div style={{ marginTop: 6, marginLeft: 20 }}>
      <div style={{
        border: '1px solid #fde68a',
        background: '#fffbeb',
        borderRadius: 8,
        padding: '10px 12px',
        fontSize: 12,
        color: '#374151',
      }}>
        <div style={{ fontWeight: 600, marginBottom: 4, color: '#92400e' }}>
          Guided verification ready
        </div>
        <div style={{ lineHeight: 1.5, marginBottom: 8 }}>
          {fields.length} field{fields.length !== 1 ? 's' : ''} to confirm in{' '}
          <span style={{ fontWeight: 500 }}>{label || docTitle}</span>.{' '}
          The test case will be saved only after you finish reviewing each value in the document.
        </div>
        <button
          onClick={handleStart}
          className="chat-action-btn"
          style={{ fontSize: 12, padding: '6px 16px' }}
        >
          Open document to verify
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Exported single-tool status line — used for interleaved segment rendering
// ---------------------------------------------------------------------------

export function ToolStatusLine({
  call,
  result,
  isActive,
  onConfirm,
}: {
  call?: ToolCallInfo
  result?: ToolResultInfo
  isActive?: boolean
  onConfirm?: (message: string) => void
}) {
  const { viewDocument, setHighlightTerms, setWorkspaceMode, setVerificationSession } = useWorkspace()
  const name = result?.tool_name || call?.tool_name || 'unknown'
  const meta = getMeta(name)
  const accent = CATEGORY_ACCENT[meta.category]
  const args = call?.args || {}
  const obj = result?.content as Record<string, unknown> | undefined
  const isError = Boolean(obj?.error)

  const needsConfirmation = !isActive && obj?.needs_confirmation === true

  const activeHint = isActive ? getActiveHint(name, args) : ''
  const { text: summaryText, qualityHint } = result
    ? summarizeResult(name, result.content, result.quality ?? null)
    : { text: '', qualityHint: '' }

  const kbActions: KBSourceActions = { viewDocument, setHighlightTerms, setWorkspaceMode }

  const verificationActions: VerificationLauncherActions = {
    viewDocument,
    setWorkspaceMode,
    openVerification: (sessionId: string) => {
      // Seed a minimal session placeholder; LeftPanel/DocumentViewer will
      // fetch the full session from the backend and keep it fresh.
      setVerificationSession({
        uuid: sessionId,
        search_set_uuid: String(obj?.extraction_set_uuid || ''),
        document_uuid: String(obj?.document_uuid || ''),
        document_title: String(obj?.document_title || ''),
        label: String(obj?.label || ''),
        status: 'pending',
        test_case_uuid: null,
        fields: ((obj?.fields as Array<Record<string, unknown>>) || []).map((f) => ({
          key: String(f.key),
          extracted: String(f.extracted ?? ''),
          expected: null,
          status: 'pending',
        })),
        all_resolved: false,
        created_at: null,
        updated_at: null,
      })
    },
  }

  return (
    <div>
      {/* Status line */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 13, lineHeight: '20px', minHeight: 22,
      }}>
        {/* Activity indicator */}
        {isActive ? (
          <Loader2
            size={12}
            style={{ animation: 'spin 1s linear infinite', color: accent, flexShrink: 0 }}
          />
        ) : (
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: isError ? '#ef4444' : accent,
            flexShrink: 0, opacity: 0.5,
          }} />
        )}

        {/* Label — active shows present tense + context hint, done shows result summary */}
        {isActive ? (
          <>
            <span style={{ color: '#374151', fontWeight: 500 }}>
              {meta.label}
            </span>
            {activeHint && (
              <span style={{ color: '#6b7280', fontStyle: 'italic' }}>
                {activeHint}
              </span>
            )}
          </>
        ) : (
          <>
            <span style={{ color: '#6b7280' }}>
              {summaryText || meta.label}
            </span>
            {qualityHint && (
              <>
                <span style={{ color: '#d1d5db' }}>&middot;</span>
                <span style={{ color: '#9ca3af', fontSize: 12 }}>
                  {qualityHint}
                </span>
              </>
            )}
          </>
        )}

        <span style={{ flex: 1 }} />

        {/* Per-result copy button — shown on status line for tools without rich content blocks */}
        {result && !isActive && hasCopyableContent(name, result.content) &&
          !hasRichContent(name, obj) && (
          <CopyButton
            text={toolResultToText(name, result.content)}
            label="Copy result"
          />
        )}

        {/* Quality badge — compact, with tooltip for details */}
        {result?.quality && (
          <QualityBadge quality={result.quality as QualityMeta} />
        )}
      </div>

      {/* Auto-shown rich content (copy/export buttons are inside each block) */}
      {result && name === 'run_extraction' && obj?.entities != null && (
        <ExtractionContent content={obj} />
      )}
      {result && name === 'search_knowledge_base' && (
        <KBPassages content={result.content} actions={kbActions} />
      )}
      {result && name === 'get_workflow_status' && obj?.status === 'completed' && obj?.output != null && (
        <WorkflowOutput content={obj} />
      )}
      {result && name === 'propose_test_case' && obj?.verification_session_id != null && (
        <VerificationLauncher content={obj} actions={verificationActions} />
      )}

      {/* Confirmation buttons for write tools awaiting user approval */}
      {needsConfirmation && onConfirm && (
        <div style={{ display: 'flex', gap: 6, marginTop: 6, marginLeft: 20 }}>
          <button
            onClick={() => onConfirm('Yes, go ahead')}
            className="chat-action-btn"
            style={{ fontSize: 12, padding: '5px 14px' }}
          >
            Confirm
          </button>
          <button
            onClick={() => onConfirm('No, cancel that')}
            style={{
              padding: '5px 14px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
              borderRadius: 8, border: '1px solid #d1d5db',
              background: '#fff', color: '#374151', cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Grouped display — fallback for persisted messages without segments
// ---------------------------------------------------------------------------

interface Props {
  toolCalls: ToolCallInfo[]
  toolResults: ToolResultInfo[]
  isStreaming?: boolean
}

export function ToolCallDisplay({ toolCalls, toolResults, isStreaming }: Props) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  if (toolCalls.length === 0 && toolResults.length === 0) return null

  const resultMap = new Map(toolResults.map((r) => [r.tool_call_id, r]))

  const allCallIds = new Set([
    ...toolResults.map((r) => r.tool_call_id),
    ...toolCalls.map((c) => c.tool_call_id),
  ])

  const toggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, margin: '6px 0' }}>
      {[...allCallIds].map((callId) => {
        const result = resultMap.get(callId)
        const call = toolCalls.find((c) => c.tool_call_id === callId)
        const name = result?.tool_name || call?.tool_name || 'unknown'
        const isActive = !result && isStreaming
        const expanded = expandedIds.has(callId)
        const expandable = result && hasExpandableContent(name, result.content)

        return (
          <div key={callId}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <div style={{ flex: 1 }}>
                <ToolStatusLine call={call} result={result} isActive={isActive} />
              </div>
              {expandable && (
                <button
                  onClick={() => toggle(callId)}
                  style={{
                    display: 'flex', alignItems: 'center',
                    background: 'none', border: 'none', padding: 0,
                    cursor: 'pointer', color: '#c4c9d1', flexShrink: 0,
                  }}
                >
                  <ChevronRight
                    size={12}
                    style={{
                      transition: 'transform 0.15s',
                      transform: expanded ? 'rotate(90deg)' : 'none',
                    }}
                  />
                </button>
              )}
            </div>
            {expanded && result && expandable && (
              renderExpandedDetails(name, result.content)
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Expandable details for list-type results
// ---------------------------------------------------------------------------

function hasExpandableContent(toolName: string, content: unknown): boolean {
  if (toolName === 'run_extraction') return false
  if (toolName === 'search_knowledge_base') return false
  if (Array.isArray(content) && content.length > 0) return true
  if (toolName === 'list_documents') {
    const obj = content as Record<string, unknown>
    return Array.isArray(obj?.documents) && obj.documents.length > 0
  }
  return false
}

function renderExpandedDetails(toolName: string, content: unknown): ReactNode {
  const obj = content as Record<string, unknown>

  if (
    ['search_documents', 'list_extraction_sets', 'list_workflows', 'list_knowledge_bases', 'search_library'].includes(toolName) &&
    Array.isArray(content)
  ) {
    if (content.length === 0) return null
    return (
      <div style={{ marginTop: 2, marginLeft: 20, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {(content as Array<Record<string, unknown>>).slice(0, 10).map((item, i) => (
          <div key={i} style={{ fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: '#d1d5db' }}>&middot;</span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {String(item.title || item.name || item.uuid || 'Untitled')}
            </span>
            {typeof item.extension === 'string' && (
              <span style={{ fontSize: 9, color: '#9ca3af', textTransform: 'uppercase' }}>
                {item.extension.replace('.', '')}
              </span>
            )}
          </div>
        ))}
        {content.length > 10 && (
          <div style={{ fontSize: 10, color: '#9ca3af', marginLeft: 10 }}>+{content.length - 10} more</div>
        )}
      </div>
    )
  }

  if (toolName === 'list_documents') {
    const docs = Array.isArray(obj.documents) ? obj.documents : []
    if (docs.length === 0) return null
    return (
      <div style={{ marginTop: 2, marginLeft: 20, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {(docs as Array<Record<string, unknown>>).slice(0, 10).map((item, i) => (
          <div key={i} style={{ fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: '#d1d5db' }}>&middot;</span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {String(item.title || item.name || 'Untitled')}
            </span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <pre style={{
      marginTop: 2, marginLeft: 20, fontSize: 10, lineHeight: 1.4,
      color: '#9ca3af', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      maxHeight: 150, overflow: 'auto',
    }}>
      {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
    </pre>
  )
}
