import { useState } from 'react'
import {
  ChevronRight, Loader2, CheckCircle2, AlertCircle, CircleDashed,
  Search, Database, Zap, FolderPlus, Play,
} from 'lucide-react'
import { QualityBadge } from './QualityBadge'
import type { ToolCallInfo, ToolResultInfo, QualityMeta } from '../../types/chat'

// ---------------------------------------------------------------------------
// Tool metadata: labels, categories, icons
// ---------------------------------------------------------------------------

type ToolCategory = 'read' | 'extract' | 'write' | 'workflow'

interface ToolMeta {
  label: string
  category: ToolCategory
}

const TOOL_META: Record<string, ToolMeta> = {
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

const CATEGORY_STYLE: Record<ToolCategory, { accent: string; bg: string; border: string; Icon: typeof Search }> = {
  read:     { accent: '#3b82f6', bg: 'rgba(59,130,246,0.04)',  border: 'rgba(59,130,246,0.15)',  Icon: Search },
  extract:  { accent: '#f59e0b', bg: 'rgba(245,158,11,0.04)', border: 'rgba(245,158,11,0.15)', Icon: Zap },
  write:    { accent: '#22c55e', bg: 'rgba(34,197,94,0.04)',   border: 'rgba(34,197,94,0.15)',  Icon: FolderPlus },
  workflow: { accent: '#8b5cf6', bg: 'rgba(139,92,246,0.04)',  border: 'rgba(139,92,246,0.15)', Icon: Play },
}

function getMeta(name: string): ToolMeta {
  return TOOL_META[name] || { label: name.replace(/_/g, ' '), category: 'read' as ToolCategory }
}

// ---------------------------------------------------------------------------
// Tool-specific result summaries
// ---------------------------------------------------------------------------

function summarizeResult(toolName: string, content: unknown): string {
  if (content == null) return 'No results'
  const obj = content as Record<string, unknown>

  if (obj.error) return `Error: ${obj.error}`
  if (obj.needs_confirmation) return obj.preview ? String(obj.preview) : 'Awaiting confirmation'
  if (obj.message && typeof obj.message === 'string') return obj.message

  switch (toolName) {
    case 'search_documents':
    case 'list_extraction_sets':
    case 'list_workflows':
    case 'list_knowledge_bases':
    case 'search_library': {
      if (Array.isArray(content)) {
        const n = content.length
        if (n === 0) return 'No results found'
        const type = toolName === 'search_documents' ? 'document' :
          toolName === 'list_extraction_sets' ? 'extraction set' :
          toolName === 'list_workflows' ? 'workflow' :
          toolName === 'list_knowledge_bases' ? 'knowledge base' : 'item'
        return `${n} ${type}${n !== 1 ? 's' : ''} found`
      }
      break
    }
    case 'list_documents': {
      const docs = Array.isArray(obj.documents) ? obj.documents.length : 0
      const folders = Array.isArray(obj.folders) ? obj.folders.length : 0
      const parts: string[] = []
      if (docs > 0) parts.push(`${docs} document${docs !== 1 ? 's' : ''}`)
      if (folders > 0) parts.push(`${folders} folder${folders !== 1 ? 's' : ''}`)
      return parts.length > 0 ? parts.join(', ') : 'Empty folder'
    }
    case 'search_knowledge_base': {
      if (Array.isArray(content)) {
        const n = content.length
        return n > 0 ? `${n} relevant passage${n !== 1 ? 's' : ''} found` : 'No matching content'
      }
      break
    }
    case 'get_document_text':
      return obj.truncated
        ? `${((obj.total_chars as number) / 1000).toFixed(0)}K chars (truncated)`
        : `${((obj.total_chars as number) / 1000).toFixed(0)}K chars`
    case 'run_extraction': {
      const count = (obj.entity_count as number) || 0
      const docs = Array.isArray(obj.documents) ? obj.documents.length : 0
      return `${count} entit${count !== 1 ? 'ies' : 'y'} from ${docs} doc${docs !== 1 ? 's' : ''}`
    }
    case 'get_quality_info':
      if (obj.score != null) return `Score: ${Math.round(obj.score as number)}/100`
      return obj.note ? String(obj.note) : 'No validation data'
    case 'create_knowledge_base':
    case 'add_documents_to_kb':
    case 'add_url_to_kb':
      return obj.message ? String(obj.message) : 'Done'
    case 'run_workflow':
      return obj.session_id ? `Started (session: ${(obj.session_id as string).slice(0, 8)}...)` : 'Started'
    case 'get_workflow_status': {
      const status = obj.status as string
      if (status === 'completed') return 'Completed'
      if (status === 'paused') return 'Paused — awaiting approval'
      if (status === 'failed') return 'Failed'
      const done = (obj.steps_completed as number) || 0
      const total = (obj.steps_total as number) || 0
      return `Running (${done}/${total} steps)`
    }
  }

  // Generic fallback
  if (Array.isArray(content)) {
    return content.length > 0 ? `${content.length} results` : 'No results'
  }
  return 'Done'
}

// ---------------------------------------------------------------------------
// Format tool args for display
// ---------------------------------------------------------------------------

function formatArgs(toolName: string, args: Record<string, unknown>): string {
  // Show the most relevant arg per tool
  const q = args.query || args.search || args.title || args.url
  if (typeof q === 'string') return q.length > 50 ? q.slice(0, 47) + '...' : q

  if (args.document_uuid && typeof args.document_uuid === 'string')
    return args.document_uuid.slice(0, 12) + '...'
  if (args.kb_uuid && typeof args.kb_uuid === 'string')
    return `KB: ${(args.kb_uuid as string).slice(0, 8)}...`

  const parts: string[] = []
  for (const [key, value] of Object.entries(args)) {
    if (value == null || key === 'context') continue
    const v = typeof value === 'string' ? value : JSON.stringify(value)
    if (v.length > 50) continue
    parts.push(v)
    if (parts.length >= 2) break
  }
  return parts.join(', ')
}

// ---------------------------------------------------------------------------
// Rich result renderers
// ---------------------------------------------------------------------------

function renderExtractionTable(content: Record<string, unknown>): JSX.Element | null {
  const entities = content.entities as Array<Record<string, unknown>> | undefined
  if (!entities || entities.length === 0) return null

  const fields = (content.fields as string[]) || Object.keys(entities[0])
  if (fields.length === 0) return null

  return (
    <div style={{ overflowX: 'auto', marginTop: 6 }}>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: 11,
        lineHeight: 1.4,
      }}>
        <thead>
          <tr>
            {fields.map((f) => (
              <th key={f} style={{
                textAlign: 'left',
                padding: '4px 8px',
                borderBottom: '2px solid #e5e7eb',
                fontWeight: 600,
                color: '#374151',
                whiteSpace: 'nowrap',
              }}>
                {f}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entities.slice(0, 20).map((entity, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
              {fields.map((f) => (
                <td key={f} style={{
                  padding: '3px 8px',
                  color: '#4b5563',
                  maxWidth: 200,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {entity[f] != null ? String(entity[f]) : <span style={{ color: '#d1d5db' }}>--</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {entities.length > 20 && (
        <div style={{ color: '#9ca3af', fontSize: 10, marginTop: 4 }}>
          Showing 20 of {entities.length} entities
        </div>
      )}
    </div>
  )
}

function renderDocumentList(content: unknown): JSX.Element | null {
  const items = Array.isArray(content) ? content : null
  if (!items || items.length === 0) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>
      {items.slice(0, 15).map((item: Record<string, unknown>, i: number) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#4b5563' }}>
          <span style={{
            display: 'inline-block',
            padding: '0 4px',
            borderRadius: 3,
            background: '#f3f4f6',
            fontSize: 10,
            fontWeight: 500,
            color: '#6b7280',
            textTransform: 'uppercase',
          }}>
            {String(item.extension || item.kind || '').replace('.', '')}
          </span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {String(item.title || item.name || item.uuid || 'Untitled')}
          </span>
        </div>
      ))}
      {items.length > 15 && (
        <div style={{ color: '#9ca3af', fontSize: 10 }}>+{items.length - 15} more</div>
      )}
    </div>
  )
}

function renderExpandedContent(toolName: string, content: unknown): JSX.Element {
  const obj = content as Record<string, unknown>

  // Extraction: render as table
  if (toolName === 'run_extraction' && obj?.entities) {
    const table = renderExtractionTable(obj)
    if (table) return table
  }

  // Search results: render as compact list
  if (
    ['search_documents', 'list_extraction_sets', 'list_workflows', 'list_knowledge_bases', 'search_library'].includes(toolName) &&
    Array.isArray(content)
  ) {
    const list = renderDocumentList(content)
    if (list) return list
  }

  // KB search: show passages
  if (toolName === 'search_knowledge_base' && Array.isArray(content)) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
        {(content as Array<Record<string, unknown>>).slice(0, 5).map((chunk, i) => (
          <div key={i} style={{ fontSize: 11, lineHeight: 1.5, color: '#4b5563' }}>
            <div style={{ fontWeight: 500, color: '#6b7280', fontSize: 10, marginBottom: 2 }}>
              {String(chunk.source_name || 'Source')}
            </div>
            <div style={{
              padding: '4px 8px',
              background: '#fafafa',
              borderRadius: 4,
              borderLeft: '2px solid #e5e7eb',
            }}>
              {String(chunk.content || '').slice(0, 300)}
              {String(chunk.content || '').length > 300 ? '...' : ''}
            </div>
          </div>
        ))}
      </div>
    )
  }

  // Default: JSON with better formatting
  return (
    <pre style={{
      marginTop: 6,
      fontSize: 11,
      lineHeight: 1.5,
      color: '#6b7280',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      maxHeight: 200,
      overflow: 'auto',
    }}>
      {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
    </pre>
  )
}

// ---------------------------------------------------------------------------
// Main component
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, margin: '8px 0' }}>
      {[...allCallIds].map((callId) => {
        const result = resultMap.get(callId)
        const call = toolCalls.find((c) => c.tool_call_id === callId)
        const name = result?.tool_name || call?.tool_name || 'unknown'
        const meta = getMeta(name)
        const catStyle = CATEGORY_STYLE[meta.category]
        const CatIcon = catStyle.Icon
        const isActive = !result && isStreaming
        const expanded = expandedIds.has(callId)
        const args = call?.args || {}
        const argsStr = formatArgs(name, args)
        const isConfirmation = result && typeof result.content === 'object' &&
          result.content !== null && (result.content as Record<string, unknown>).needs_confirmation === true

        return (
          <div
            key={callId}
            style={{
              background: isConfirmation ? 'rgba(245,158,11,0.06)' : catStyle.bg,
              border: `1px solid ${isConfirmation ? 'rgba(245,158,11,0.3)' : catStyle.border}`,
              borderLeft: isConfirmation ? '3px solid #f59e0b' : undefined,
              borderRadius: 'var(--ui-radius, 8px)',
              padding: '6px 10px',
              fontSize: 12,
              transition: 'border-color 0.15s',
            }}
          >
            {/* Header row */}
            <button
              onClick={() => result && toggle(callId)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                width: '100%',
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: result ? 'pointer' : 'default',
                color: 'inherit',
                fontSize: 12,
                textAlign: 'left',
                fontFamily: 'inherit',
              }}
            >
              {isActive ? (
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite', flexShrink: 0, color: catStyle.accent, opacity: 0.7 }} />
              ) : isConfirmation ? (
                <CircleDashed size={14} style={{ color: '#f59e0b', flexShrink: 0 }} />
              ) : result ? (
                <CheckCircle2 size={14} style={{ color: catStyle.accent, flexShrink: 0 }} />
              ) : (
                <CatIcon size={14} style={{ color: '#94a3b8', flexShrink: 0 }} />
              )}

              <span style={{ fontWeight: 500, color: '#374151' }}>
                {meta.label}
              </span>

              {argsStr && (
                <span style={{
                  color: '#94a3b8',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flex: 1,
                  fontStyle: 'italic',
                }}>
                  {argsStr}
                </span>
              )}

              {result && (
                <span style={{ color: '#6b7280', marginLeft: 'auto', whiteSpace: 'nowrap', fontSize: 11 }}>
                  {summarizeResult(name, result.content)}
                </span>
              )}

              {result?.quality && (
                <QualityBadge quality={result.quality as QualityMeta} />
              )}

              {result && (
                <ChevronRight
                  size={14}
                  style={{
                    flexShrink: 0,
                    transition: 'transform 0.15s',
                    transform: expanded ? 'rotate(90deg)' : 'none',
                    opacity: 0.4,
                    color: catStyle.accent,
                  }}
                />
              )}
            </button>

            {/* Expanded details — rich rendering */}
            {expanded && result && (
              <div style={{
                marginTop: 6,
                paddingTop: 6,
                borderTop: `1px solid ${catStyle.border}`,
                maxHeight: 300,
                overflow: 'auto',
              }}>
                {renderExpandedContent(name, result.content)}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
