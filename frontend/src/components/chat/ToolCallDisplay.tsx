import { useState } from 'react'
import { ChevronRight, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { QualityBadge } from './QualityBadge'
import type { ToolCallInfo, ToolResultInfo } from '../../types/chat'

/** Human-readable labels for tool names. */
const TOOL_LABELS: Record<string, string> = {
  search_documents: 'Searching documents',
  list_documents: 'Listing documents',
  search_knowledge_base: 'Querying knowledge base',
  list_knowledge_bases: 'Listing knowledge bases',
  list_extraction_sets: 'Listing extraction sets',
  list_workflows: 'Listing workflows',
  get_quality_info: 'Checking quality',
  search_library: 'Searching library',
  run_extraction: 'Running extraction',
  get_document_text: 'Reading document',
  create_knowledge_base: 'Creating knowledge base',
  add_documents_to_kb: 'Adding documents to KB',
  add_url_to_kb: 'Adding URL to KB',
  run_workflow: 'Running workflow',
  get_workflow_status: 'Checking workflow status',
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name.replace(/_/g, ' ')
}

/** Format tool args as a short human-readable string. */
function formatArgs(args: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(args)) {
    if (value == null || key === 'context') continue
    const v = typeof value === 'string' ? value : JSON.stringify(value)
    if (v.length > 60) continue // skip large values
    parts.push(`${key}: ${v}`)
  }
  return parts.join(', ')
}

/** Summarize tool result content as a short description. */
function summarizeResult(content: unknown): string {
  if (content == null) return 'No results'
  if (Array.isArray(content)) {
    if (content.length === 0) return 'No results'
    return `${content.length} result${content.length === 1 ? '' : 's'}`
  }
  if (typeof content === 'object') {
    const obj = content as Record<string, unknown>
    if (obj.error) return `Error: ${obj.error}`
    if (obj.note) return String(obj.note)
    const keys = Object.keys(obj)
    // Check for list-like fields
    for (const k of keys) {
      if (Array.isArray(obj[k])) {
        const arr = obj[k] as unknown[]
        return `${arr.length} ${k}`
      }
    }
    return `${keys.length} field${keys.length === 1 ? '' : 's'}`
  }
  if (typeof content === 'string') {
    return content.length > 80 ? content.slice(0, 77) + '...' : content
  }
  return String(content)
}

interface Props {
  toolCalls: ToolCallInfo[]
  toolResults: ToolResultInfo[]
  isStreaming?: boolean
}

export function ToolCallDisplay({ toolCalls, toolResults, isStreaming }: Props) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  if (toolCalls.length === 0 && toolResults.length === 0) return null

  const resultMap = new Map(toolResults.map((r) => [r.tool_call_id, r]))

  // Build a unified list: completed results + active calls
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
        const isActive = !result && isStreaming
        const expanded = expandedIds.has(callId)
        const args = call?.args || {}
        const argsStr = formatArgs(args)

        return (
          <div
            key={callId}
            style={{
              background: 'rgba(148,163,184,0.06)',
              border: '1px solid rgba(148,163,184,0.15)',
              borderRadius: 'var(--ui-radius, 8px)',
              padding: '6px 10px',
              fontSize: 12,
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
              }}
            >
              {isActive ? (
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite', flexShrink: 0, opacity: 0.6 }} />
              ) : result ? (
                <CheckCircle2 size={14} style={{ color: '#22c55e', flexShrink: 0 }} />
              ) : (
                <AlertCircle size={14} style={{ color: '#94a3b8', flexShrink: 0 }} />
              )}

              <span style={{ fontWeight: 500 }}>
                {toolLabel(name)}
              </span>

              {argsStr && (
                <span style={{ color: '#94a3b8', fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  {argsStr}
                </span>
              )}

              {result && (
                <span style={{ color: '#94a3b8', marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                  {summarizeResult(result.content)}
                </span>
              )}

              {result?.quality && (
                <QualityBadge quality={result.quality} />
              )}

              {result && (
                <ChevronRight
                  size={14}
                  style={{
                    flexShrink: 0,
                    transition: 'transform 0.15s',
                    transform: expanded ? 'rotate(90deg)' : 'none',
                    opacity: 0.5,
                  }}
                />
              )}
            </button>

            {/* Expanded details */}
            {expanded && result && (
              <div style={{
                marginTop: 6,
                paddingTop: 6,
                borderTop: '1px solid rgba(148,163,184,0.12)',
                color: '#94a3b8',
                fontSize: 11,
                lineHeight: 1.5,
                maxHeight: 200,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {typeof result.content === 'string'
                  ? result.content
                  : JSON.stringify(result.content, null, 2)}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
