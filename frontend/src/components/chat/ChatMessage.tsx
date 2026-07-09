import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ThumbsUp, ThumbsDown, Copy, Check, ChevronRight } from 'lucide-react'
import { submitChatFeedback } from '../../api/feedback'
import { useBranding } from '../../contexts/BrandingContext'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { ToolCallDisplay, ToolStatusLine, toolResultToText, pickHighlightPhrase } from './ToolCallDisplay'
import { renderMarkdown, THINK_BLOCK_RE, THINK_TRAILING_RE } from './markdown'
import { routeActionClick } from './actionRoute'
import type { ChatMessage as ChatMessageType, Citation, StreamSegment, ToolCallInfo, ToolResultInfo } from '../../types/chat'

const THINKING_WORDS = [
  'Thinking', 'Vandalizing', 'Pondering', 'Analyzing',
  'Processing', 'Brewing', 'Crunching', 'Conjuring',
]

function ThinkingLabel() {
  const { isCustomized } = useBranding()
  // 'Vandalizing' is a Joe Vandal in-joke — keep it off white-labeled deployments.
  const words = isCustomized ? THINKING_WORDS.filter(w => w !== 'Vandalizing') : THINKING_WORDS
  const [index, setIndex] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setIndex(i => (i + 1) % words.length)
        setFade(true)
      }, 200)
    }, 2000)
    return () => clearInterval(interval)
  }, [words.length])

  return (
    <span style={{
      opacity: fade ? 1 : 0,
      transition: 'opacity 0.2s ease',
      display: 'inline-block',
      minWidth: 80,
    }}>
      {words[index % words.length]}&hellip;
    </span>
  )
}

interface Props {
  message: ChatMessageType
  messageIndex?: number
  conversationUuid?: string
  streamingThinking?: string
  thinkingDuration?: number | null
  isStreaming?: boolean
  activeToolCalls?: ToolCallInfo[]
  toolResults?: ToolResultInfo[]
  /** Ordered stream segments for interleaved rendering */
  streamSegments?: StreamSegment[]
  /** Callback to inject a message into the chat (used for confirmation buttons) */
  onSendMessage?: (message: string) => void
}

export function ChatMessage({
  message, messageIndex, conversationUuid, streamingThinking,
  thinkingDuration, isStreaming: isStreamingProp, activeToolCalls,
  toolResults, streamSegments, onSendMessage,
}: Props) {
  const isUser = message.role === 'user'
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null)
  const [copied, setCopied] = useState(false)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState('')
  const [commentSent, setCommentSent] = useState(false)
  const [thinkingExpanded, setThinkingExpanded] = useState(false)
  const [openCitation, setOpenCitation] = useState<number | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const certPanel = useCertificationPanel()
  const { setWorkspaceMode, viewDocument, setHighlightTerms } = useWorkspace()
  const { toast } = useToast()

  const thinkingText = streamingThinking || message.thinking || ''
  const duration = thinkingDuration ?? message.thinking_duration ?? null
  const hasThinking = thinkingText.length > 0

  // Determine which segments to use: streaming > persisted > none
  const segments = streamSegments || message.segments || null

  // For non-segment fallback: full rendered HTML
  const renderedHtml = useMemo(() => {
    if (isUser || segments) return null
    return renderMarkdown(message.content)
  }, [message.content, isUser, segments])

  // Handle action button clicks via event delegation — robust across
  // streaming deltas and dangerouslySetInnerHTML remounts.
  const handleActionClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = (e.target as HTMLElement).closest<HTMLElement>('[data-action]')
    if (!target) return
    const route = routeActionClick(target.getAttribute('data-action'), target.textContent || '')
    if (route.kind === 'cert') certPanel.openPanel()
    else if (route.kind === 'files') setWorkspaceMode('files')
    // Improvised action buttons (create-kb, build-workflow, …) have no dedicated
    // route; send their label so the assistant performs them via its tools
    // instead of the click dead-ending.
    else if (route.kind === 'send' && onSendMessage) onSendMessage(route.message)
  }, [certPanel, setWorkspaceMode, onSendMessage])

  const handleFeedback = async (rating: 'up' | 'down') => {
    const prev = feedback
    setFeedback(rating)
    try {
      await submitChatFeedback({
        conversation_uuid: conversationUuid,
        message_index: messageIndex,
        rating,
      })
    } catch {
      // Revert the optimistic highlight so the user knows it didn't save.
      setFeedback(prev)
      toast('Could not save your feedback. Please try again.', 'error')
      return
    }
    if (rating === 'down') setShowComment(true)
  }

  const handleSubmitComment = async () => {
    if (!comment.trim()) return
    try {
      await submitChatFeedback({
        conversation_uuid: conversationUuid,
        message_index: messageIndex,
        rating: 'down',
        comment: comment.trim(),
      })
      setCommentSent(true)
      setShowComment(false)
    } catch {
      toast('Could not send your comment. Please try again.', 'error')
    }
  }

  // Open the cited document in the viewer and highlight the cited passage.
  const handleCitationClick = (c: Citation) => {
    if (!c.document_id) return
    setWorkspaceMode('files')
    viewDocument(c.document_id, c.document_title)
    if (c.content_preview) setHighlightTerms([pickHighlightPhrase(c.content_preview)])
  }

  const handleCopy = () => {
    // Build full message text including tool results
    const segs = segments || message.segments
    let text: string
    if (segs && segs.length > 0) {
      const parts: string[] = []
      for (const seg of segs) {
        if (seg.kind === 'text') {
          const cleaned = seg.content.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '').trim()
          if (cleaned) parts.push(cleaned)
        } else if (seg.kind === 'tool_result') {
          const body = toolResultToText(seg.result.tool_name, seg.result.content)
          if (body) parts.push(body)
        }
      }
      text = parts.join('\n\n')
    } else {
      // Fallback: message.content + any tool results
      const parts = [message.content]
      for (const r of (message.tool_results || [])) {
        const body = toolResultToText(r.tool_name, r.content)
        if (body) parts.push(body)
      }
      text = parts.join('\n\n')
    }
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Build a result lookup from both streaming and persisted sources
  const resultMap = useMemo(() => {
    const map = new Map<string, ToolResultInfo>()
    for (const r of (toolResults || message.tool_results || [])) {
      map.set(r.tool_call_id, r)
    }
    // Also gather from segments
    if (segments) {
      for (const seg of segments) {
        if (seg.kind === 'tool_result') map.set(seg.result.tool_call_id, seg.result)
      }
    }
    return map
  }, [toolResults, message.tool_results, segments])

  // Active call IDs (no result yet)
  const activeCallIds = useMemo(() => {
    const ids = new Set<string>()
    for (const c of (activeToolCalls || [])) ids.add(c.tool_call_id)
    return ids
  }, [activeToolCalls])

  // Duplicate confirmation cards to suppress. A model may call the same write
  // tool more than once in a single turn (e.g. a preview followed by a
  // self-confirm the gate downgrades to another preview), which would render
  // two identical "Confirm / Cancel" cards for one action. Keep only the first
  // occurrence of each awaiting-confirmation action within this message.
  const suppressedConfirmCallIds = useMemo(() => {
    const suppressed = new Set<string>()
    if (!segments) return suppressed
    const seen = new Set<string>()
    for (const seg of segments) {
      if (seg.kind !== 'tool_call') continue
      const content = resultMap.get(seg.call.tool_call_id)?.content as
        | Record<string, unknown>
        | undefined
      if (!content || content.needs_confirmation !== true) continue
      const key = `${seg.call.tool_name}|${String(content.preview ?? '')}`
      if (seen.has(key)) suppressed.add(seg.call.tool_call_id)
      else seen.add(key)
    }
    return suppressed
  }, [segments, resultMap])

  return (
    <div
      style={{
        padding: 15,
        marginBottom: isUser ? 10 : 15,
        color: isUser ? 'white' : 'black',
        backgroundColor: isUser ? '#191919' : '#00000008',
        borderLeft: isUser ? '7px solid var(--highlight-color, #f1b300)' : 'none',
        borderRadius: 'var(--ui-radius, 12px)',
      }}
    >
      {isUser ? (
        <div className="whitespace-pre-wrap break-words text-sm leading-relaxed select-text">
          {message.content}
        </div>
      ) : (
        <>
          {/* Collapsible thinking trace */}
          {hasThinking && (
            <div style={{ marginBottom: 10 }}>
              <button
                type="button"
                onClick={() => setThinkingExpanded(!thinkingExpanded)}
                aria-expanded={thinkingExpanded}
                aria-label={thinkingExpanded ? 'Collapse thinking' : 'Expand thinking'}
                className={duration == null ? 'thinking-shimmer' : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '2px 0',
                  fontSize: 12,
                  color: '#6b7280',
                  fontFamily: 'inherit',
                  transition: 'color 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = '#4b5563' }}
                onMouseLeave={e => { e.currentTarget.style.color = '#6b7280' }}
              >
                <ChevronRight
                  size={14}
                  style={{
                    transition: 'transform 0.2s ease',
                    transform: thinkingExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                  }}
                />
                {duration != null
                  ? `Thought for ${duration < 1 ? 'less than a second' : `${Math.round(duration)} second${Math.round(duration) !== 1 ? 's' : ''}`}`
                  : <ThinkingLabel />}
              </button>
              <div className={`thinking-collapse${thinkingExpanded ? ' open' : ''}`}>
                <div>
                  <div
                    style={{
                      marginTop: 6, padding: '10px 12px',
                      backgroundColor: '#f9fafb',
                      borderLeft: '3px solid var(--highlight-color, #eab308)',
                      borderRadius: 4, fontSize: 13, lineHeight: 1.6,
                      color: '#6b7280', fontStyle: 'italic',
                      maxHeight: 400, overflowY: 'auto',
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    }}
                    className="hide-scrollbar"
                  >
                    {thinkingText}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Interleaved segment rendering (streaming + persisted) */}
          {segments && segments.length > 0 ? (
            <div ref={contentRef} onClick={handleActionClick}>
              {segments.map((seg, i) => {
                if (seg.kind === 'text') {
                  const cleaned = seg.content.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '')
                  if (!cleaned.trim()) return null
                  const html = renderMarkdown(cleaned)
                  return (
                    <div
                      key={i}
                      className="select-text chat-markdown"
                      style={{ fontSize: 14, lineHeight: 1.6 }}
                      dangerouslySetInnerHTML={{ __html: html }}
                    />
                  )
                }
                if (seg.kind === 'queued_user') {
                  // A message the user sent while this reply was running
                  // (Phase 10) — render as a user-side chip in-position.
                  return (
                    <div key={i} className="my-2 flex justify-end">
                      <div className="max-w-[80%] rounded-lg bg-gray-100 border border-gray-200 px-3 py-1.5 text-sm text-gray-800">
                        {seg.content}
                      </div>
                    </div>
                  )
                }
                if (seg.kind === 'tool_call') {
                  // update_plan renders as the pinned checklist card, not a
                  // tool status line (uplift plan Phase 8).
                  if (seg.call.tool_name === 'update_plan') return null
                  // Drop duplicate confirmation cards for the same action.
                  if (suppressedConfirmCallIds.has(seg.call.tool_call_id)) return null
                  const result = resultMap.get(seg.call.tool_call_id)
                  const isActive = !result && (isStreamingProp || activeCallIds.has(seg.call.tool_call_id))
                  return (
                    <div key={i} style={{ margin: '4px 0' }}>
                      <ToolStatusLine call={seg.call} result={result} isActive={isActive} onConfirm={onSendMessage} />
                    </div>
                  )
                }
                // tool_result segments: skip — rendered inline with their tool_call above
                return null
              })}
              {/* Show any active tool calls that haven't appeared in segments yet */}
              {activeToolCalls && activeToolCalls.filter(
                (c) => !segments.some((s) => s.kind === 'tool_call' && s.call.tool_call_id === c.tool_call_id),
              ).map((c) => (
                <div key={c.tool_call_id} style={{ margin: '4px 0' }}>
                  <ToolStatusLine call={c} isActive />
                </div>
              ))}
            </div>
          ) : (
            /* Fallback: no segments (e.g. history loaded from backend) */
            <>
              {message.content && (
                <div
                  ref={contentRef}
                  onClick={handleActionClick}
                  className="select-text chat-markdown"
                  style={{ fontSize: 14, lineHeight: 1.6 }}
                  dangerouslySetInnerHTML={{ __html: renderedHtml! }}
                />
              )}

              {(() => {
                const calls = activeToolCalls || message.tool_calls || []
                const results = toolResults || message.tool_results || []
                if (calls.length === 0 && results.length === 0) return null
                return (
                  <ToolCallDisplay
                    toolCalls={calls}
                    toolResults={results}
                    isStreaming={isStreamingProp}
                  />
                )
              })()}
            </>
          )}

          {message.citations && message.citations.length > 0 && (() => {
            const open = openCitation !== null ? message.citations[openCitation] : null
            const openPreview = open?.content_preview?.trim() || ''
            return (
              <div style={{ marginTop: 8 }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  <span style={{ fontSize: 11, color: '#6b7280', alignSelf: 'center', marginRight: 2 }}>
                    Sources:
                  </span>
                  {message.citations.map((c, i) => {
                    const locator = typeof c.page === 'number' ? `p. ${c.page}` : (c.sheet || null)
                    const label = locator ? `${c.document_title} · ${locator}` : c.document_title
                    const preview = c.content_preview || ''
                    const key = `${c.chunk_id ?? c.document_id ?? i}`
                    const chipBase = {
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '2px 8px', fontSize: 11, fontWeight: 500,
                      borderRadius: 999, transition: 'all 0.15s',
                    } as const
                    // URL-backed KB source: link straight out to the origin.
                    if (c.url) {
                      return (
                        <a
                          key={key}
                          href={c.url}
                          target="_blank"
                          rel="noreferrer"
                          title={preview ? `${preview}\n\nOpens ${c.url}` : c.url}
                          style={{
                            ...chipBase,
                            backgroundColor: '#f3f4f6', color: '#374151',
                            border: '1px solid #e5e7eb',
                            cursor: 'pointer', textDecoration: 'none',
                          }}
                        >
                          {label}
                        </a>
                      )
                    }
                    const isOpen = openCitation === i
                    return (
                      <button
                        key={key}
                        type="button"
                        title={preview}
                        aria-expanded={isOpen}
                        onClick={() => setOpenCitation(isOpen ? null : i)}
                        style={{
                          ...chipBase,
                          backgroundColor: isOpen ? '#e0e7ff' : '#f3f4f6',
                          color: isOpen ? '#3730a3' : '#374151',
                          border: `1px solid ${isOpen ? '#c7d2fe' : '#e5e7eb'}`,
                          cursor: 'pointer',
                        }}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
                {open && (
                  <div style={{
                    marginTop: 6, padding: '8px 10px', fontSize: 12, lineHeight: 1.5,
                    color: '#374151', backgroundColor: '#f9fafb',
                    border: '1px solid #e5e7eb', borderRadius: 8,
                    whiteSpace: 'pre-wrap' as const,
                  }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>
                      {open.document_title}
                      {typeof open.page === 'number' ? ` · p. ${open.page}` : (open.sheet ? ` · ${open.sheet}` : '')}
                    </div>
                    {openPreview || 'No preview available for this source.'}
                    {open.source_reference && (
                      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
                        Source: {open.source_reference}
                      </div>
                    )}
                    {open.document_id && (
                      <button
                        type="button"
                        onClick={() => handleCitationClick(open)}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          marginTop: 8, padding: '4px 10px', fontSize: 11, fontWeight: 600,
                          fontFamily: 'inherit', backgroundColor: '#fff', color: '#374151',
                          border: '1px solid #d1d5db', borderRadius: 6, cursor: 'pointer',
                        }}
                      >
                        Open the source
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })()}

          {/* Feedback bar - hidden during streaming */}
          {!isStreamingProp && message.content && <div style={{
            display: 'flex', alignItems: 'center', gap: 4, marginTop: 10,
            paddingTop: 8, borderTop: '1px solid #00000010',
          }}>
            <button
              type="button"
              onClick={() => handleFeedback('up')}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 6, border: 'none',
                background: feedback === 'up' ? '#dcfce7' : 'transparent',
                color: feedback === 'up' ? '#16a34a' : '#6b7280',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              title="Good response"
              aria-label="Good response"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              type="button"
              onClick={() => handleFeedback('down')}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 6, border: 'none',
                background: feedback === 'down' ? '#fee2e2' : 'transparent',
                color: feedback === 'down' ? '#dc2626' : '#6b7280',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              title="Poor response"
              aria-label="Poor response"
            >
              <ThumbsDown size={14} />
            </button>
            <div style={{ flex: 1 }} />
            <button
              type="button"
              onClick={handleCopy}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 6, border: 'none',
                background: 'transparent', color: copied ? '#16a34a' : '#6b7280',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              title="Copy message"
              aria-label="Copy message"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>}

          {/* Comment form for negative feedback */}
          {!isStreamingProp && showComment && !commentSent && (
            <div style={{
              marginTop: 8, display: 'flex', gap: 8, alignItems: 'flex-start',
            }}>
              <input
                autoFocus
                value={comment}
                onChange={e => setComment(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSubmitComment() }}
                placeholder="What went wrong? (optional)"
                aria-label="What went wrong? (optional)"
                style={{
                  flex: 1, padding: '6px 10px', borderRadius: 6,
                  border: '1px solid #d1d5db', fontSize: 13,
                }}
              />
              <button
                type="button"
                onClick={handleSubmitComment}
                style={{
                  padding: '6px 12px', borderRadius: 6, border: 'none',
                  background: '#374151', color: '#fff', fontSize: 12,
                  fontWeight: 600, cursor: 'pointer',
                }}
              >
                Send
              </button>
              <button
                type="button"
                onClick={() => setShowComment(false)}
                style={{
                  padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db',
                  background: '#fff', fontSize: 12, cursor: 'pointer',
                }}
              >
                Skip
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
