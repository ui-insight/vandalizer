import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DOMPurify from 'dompurify'
import { ThumbsUp, ThumbsDown, Copy, Check, ChevronRight } from 'lucide-react'
import { marked } from 'marked'
import { submitChatFeedback } from '../../api/feedback'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { ToolCallDisplay, ToolStatusLine, toolResultToText } from './ToolCallDisplay'
import type { ChatMessage as ChatMessageType, StreamSegment, ToolCallInfo, ToolResultInfo } from '../../types/chat'

// Matches [ACTION:type]Label[/ACTION] (correct) and also
// [Label][ACTION:type] or [Label](ACTION:type) (common LLM mistakes)
const ACTION_RE = /\[ACTION:([\w-]+)\](.*?)\[\/ACTION\]/g
const ACTION_RE_ALT = /\[([^\]]+)\]\[ACTION:([\w-]+)\]/g
const ACTION_RE_ALT2 = /\[([^\]]+)\]\(ACTION:([\w-]+)\)/g
const THINK_BLOCK_RE = /<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>\n?/g
const THINK_TRAILING_RE = /<think(?:ing)?>[\s\S]*$/

const THINKING_WORDS = [
  'Thinking', 'Vandalizing', 'Pondering', 'Analyzing',
  'Processing', 'Brewing', 'Crunching', 'Conjuring',
]

function ThinkingLabel() {
  const [index, setIndex] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setIndex(i => (i + 1) % THINKING_WORDS.length)
        setFade(true)
      }, 200)
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  return (
    <span style={{
      opacity: fade ? 1 : 0,
      transition: 'opacity 0.2s ease',
      display: 'inline-block',
      minWidth: 80,
    }}>
      {THINKING_WORDS[index]}&hellip;
    </span>
  )
}

marked.setOptions({ breaks: true, gfm: true })

/** Render a markdown string to sanitized HTML. */
function renderMarkdown(text: string): string {
  let cleaned = text.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '')
  // Canonical: [ACTION:type]Label[/ACTION]
  cleaned = cleaned.replace(ACTION_RE, (_match, type: string, label: string) =>
    `<button data-action="${type}" class="chat-action-btn">${label}</button>`
  )
  // LLM mistake: [Label][ACTION:type]
  cleaned = cleaned.replace(ACTION_RE_ALT, (_match, label: string, type: string) =>
    `<button data-action="${type}" class="chat-action-btn">${label}</button>`
  )
  // LLM mistake: [Label](ACTION:type)
  cleaned = cleaned.replace(ACTION_RE_ALT2, (_match, label: string, type: string) =>
    `<button data-action="${type}" class="chat-action-btn">${label}</button>`
  )
  return DOMPurify.sanitize(marked.parse(cleaned) as string, {
    ADD_TAGS: ['button'],
    ADD_ATTR: ['data-action'],
  })
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
  const contentRef = useRef<HTMLDivElement>(null)
  const certPanel = useCertificationPanel()
  const { setWorkspaceMode } = useWorkspace()

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
    const action = target.getAttribute('data-action')
    if (action === 'start-cert') certPanel.openPanel()
    else if (action === 'upload-docs') setWorkspaceMode('files')
  }, [certPanel, setWorkspaceMode])

  const handleFeedback = async (rating: 'up' | 'down') => {
    setFeedback(rating)
    try {
      await submitChatFeedback({
        conversation_uuid: conversationUuid,
        message_index: messageIndex,
        rating,
      })
    } catch { /* ignore */ }
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
    } catch { /* ignore */ }
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
                onClick={() => setThinkingExpanded(!thinkingExpanded)}
                aria-expanded={thinkingExpanded}
                aria-label={thinkingExpanded ? 'Collapse thinking' : 'Expand thinking'}
                className={duration == null ? 'thinking-shimmer' : undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  background: 'none', border: 'none', cursor: 'pointer',
                  padding: '2px 0', fontSize: 12, color: '#9ca3af',
                  fontFamily: 'inherit', transition: 'color 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = '#6b7280' }}
                onMouseLeave={e => { e.currentTarget.style.color = '#9ca3af' }}
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
                if (seg.kind === 'tool_call') {
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

          {/* Feedback bar - hidden during streaming */}
          {!isStreamingProp && message.content && <div style={{
            display: 'flex', alignItems: 'center', gap: 4, marginTop: 10,
            paddingTop: 8, borderTop: '1px solid #00000010',
          }}>
            <button
              onClick={() => handleFeedback('up')}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 6, border: 'none',
                background: feedback === 'up' ? '#dcfce7' : 'transparent',
                color: feedback === 'up' ? '#16a34a' : '#9ca3af',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              title="Good response"
              aria-label="Good response"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              onClick={() => handleFeedback('down')}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 6, border: 'none',
                background: feedback === 'down' ? '#fee2e2' : 'transparent',
                color: feedback === 'down' ? '#dc2626' : '#9ca3af',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              title="Poor response"
              aria-label="Poor response"
            >
              <ThumbsDown size={14} />
            </button>
            <div style={{ flex: 1 }} />
            <button
              onClick={handleCopy}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 6, border: 'none',
                background: 'transparent', color: copied ? '#16a34a' : '#9ca3af',
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
                style={{
                  flex: 1, padding: '6px 10px', borderRadius: 6,
                  border: '1px solid #d1d5db', fontSize: 13, outline: 'none',
                }}
              />
              <button
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
