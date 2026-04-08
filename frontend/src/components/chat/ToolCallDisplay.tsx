import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronRight, Loader2 } from 'lucide-react'
import { QualityBadge } from './QualityBadge'
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
  list_extraction_sets:  { label: 'Listing extraction sets',  category: 'read' },
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
// Auto-shown rich content
// ---------------------------------------------------------------------------

/** Key-value pairs for single-entity extractions, compact table for multi. */
function renderExtractionContent(content: Record<string, unknown>): ReactNode {
  const entities = content.entities as Array<Record<string, unknown>> | undefined
  if (!entities || entities.length === 0) return null
  const fields = (content.fields as string[]) || Object.keys(entities[0])
  if (fields.length === 0) return null

  // Single entity: key-value pairs
  if (entities.length === 1) {
    const entity = entities[0]
    const entries = fields
      .filter((f) => entity[f] != null && String(entity[f]).trim() !== '' && String(entity[f]) !== '--')
    const shown = entries.slice(0, 8)
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
        {remaining > 0 && (
          <div style={{ color: '#c4c9d1', fontSize: 11, marginTop: 2 }}>
            +{remaining} more fields
          </div>
        )}
      </div>
    )
  }

  // Multiple entities: compact table with limited columns
  const maxCols = 6
  const visibleFields = fields.slice(0, maxCols)
  const hiddenCols = fields.length - visibleFields.length

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
          {entities.slice(0, 12).map((entity, i) => (
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
      <div style={{ color: '#c4c9d1', fontSize: 10, marginTop: 2, display: 'flex', gap: 12 }}>
        {entities.length > 12 && <span>+{entities.length - 12} more rows</span>}
        {hiddenCols > 0 && <span>+{hiddenCols} more columns</span>}
      </div>
    </div>
  )
}

function renderKBPassages(content: unknown): ReactNode {
  if (!Array.isArray(content) || content.length === 0) return null
  const passages = content as Array<Record<string, unknown>>

  return (
    <div style={{ marginTop: 4, marginLeft: 20, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {passages.slice(0, 3).map((chunk, i) => (
        <div key={i} style={{
          fontSize: 11, lineHeight: 1.5, color: '#6b7280',
          padding: '4px 8px', borderLeft: '2px solid #e5e7eb',
          background: '#fafafa', borderRadius: '0 4px 4px 0',
        }}>
          <span style={{ fontWeight: 500, color: '#9ca3af', fontSize: 10 }}>
            {String(chunk.source_name || 'Source')}
          </span>
          <span style={{ margin: '0 6px', color: '#d1d5db' }}>&middot;</span>
          <span>{String(chunk.content || '').slice(0, 200)}{String(chunk.content || '').length > 200 ? '...' : ''}</span>
        </div>
      ))}
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
}: {
  call?: ToolCallInfo
  result?: ToolResultInfo
  isActive?: boolean
}) {
  const name = result?.tool_name || call?.tool_name || 'unknown'
  const meta = getMeta(name)
  const accent = CATEGORY_ACCENT[meta.category]
  const args = call?.args || {}
  const obj = result?.content as Record<string, unknown> | undefined
  const isError = Boolean(obj?.error)

  const activeHint = isActive ? getActiveHint(name, args) : ''
  const { text: summaryText, qualityHint } = result
    ? summarizeResult(name, result.content, result.quality ?? null)
    : { text: '', qualityHint: '' }

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

        {/* Quality badge — compact, with tooltip for details */}
        {result?.quality && (
          <QualityBadge quality={result.quality as QualityMeta} />
        )}
      </div>

      {/* Auto-shown rich content */}
      {result && name === 'run_extraction' && obj?.entities != null && (
        renderExtractionContent(obj)
      )}
      {result && name === 'search_knowledge_base' && (
        renderKBPassages(result.content)
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
