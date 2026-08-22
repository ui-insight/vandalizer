import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import DOMPurify from 'dompurify'
import { ThumbsUp, ThumbsDown, Copy, Check, ChevronRight, Eye, FileText } from 'lucide-react'
import { marked } from 'marked'
import { submitChatFeedback } from '../../api/feedback'
import { formatPageLocator } from '../../utils/pageLocator'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { citationAnchor } from '../../utils/textMatch'
import type { ChatMessage as ChatMessageType, Citation } from '../../types/chat'

const ACTION_RE = /\[ACTION:([\w-]+)\](.*?)\[\/ACTION\]/g

const THINKING_WORDS = [
  'Thinking', 'Vandalizing', 'Pondering', 'Analyzing',
  'Processing', 'Reading', 'Reviewing',
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

function CitationMenuItem({ icon, label, onClick }: {
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 6, width: '100%',
        padding: '5px 8px', border: 'none', borderRadius: 5,
        background: 'transparent', color: '#374151',
        fontSize: 12, fontFamily: 'inherit', textAlign: 'left',
        cursor: 'pointer', transition: 'background-color 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
      onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
    >
      {icon}
      {label}
    </button>
  )
}

marked.setOptions({ breaks: true, gfm: true })

interface Props {
  message: ChatMessageType
  messageIndex?: number
  conversationUuid?: string
  /** Live thinking content during streaming (before thinking is finalized) */
  streamingThinking?: string
  /** Duration in seconds (from thinking_done event or persisted) */
  thinkingDuration?: number | null
  /** Whether this message is currently streaming */
  isStreaming?: boolean
}

/** The nearest ancestor that clips its contents horizontally.
 *
 * A container with `overflow-y: auto` computes `overflow-x` to `auto` too, per
 * CSS — so the chat scroller clips sideways even though nothing asked it to,
 * and `hide-scrollbar` removes the scrollbar that would otherwise let a reader
 * reach what spilled out.
 */
function clippingAncestor(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null
  while (node && node !== document.body) {
    const { overflowX, overflowY } = getComputedStyle(node)
    if (overflowX !== 'visible' || overflowY !== 'visible') return node
    node = node.parentElement
  }
  return null
}

/** Align the menu to the pill's right edge when left-aligning would overflow.
 *
 * Returns the alignment to use. Flipping is only worth it if the menu actually
 * fits that way — otherwise it would be clipped on the other side instead, and
 * left-aligned at least keeps the first item reachable.
 */
export function menuAlignmentFor(
  pillLeft: number, pillRight: number, menuWidth: number,
  containerLeft: number, containerRight: number,
): 'left' | 'right' {
  const fitsLeftAligned = pillLeft + menuWidth <= containerRight
  if (fitsLeftAligned) return 'left'
  const fitsRightAligned = pillRight - menuWidth >= containerLeft
  return fitsRightAligned ? 'right' : 'left'
}

export function ChatMessage({ message, messageIndex, conversationUuid, streamingThinking, thinkingDuration, isStreaming: isStreamingProp }: Props) {
  const isUser = message.role === 'user'
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null)
  const [copied, setCopied] = useState(false)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState('')
  const [commentSent, setCommentSent] = useState(false)
  const [thinkingExpanded, setThinkingExpanded] = useState(false)
  const [openCitation, setOpenCitation] = useState<number | null>(null)
  // Citation whose Preview/Open chooser is showing (null = none).
  const [citationMenu, setCitationMenu] = useState<number | null>(null)
  // The menu is absolutely positioned inside the chat scroller, which clips
  // horizontally; in files mode the panel is ~half width, so the last pill on
  // a row opens a menu that runs off the edge with no scrollbar to reach it.
  const [menuAlign, setMenuAlign] = useState<'left' | 'right'>('left')
  const menuRef = useRef<HTMLDivElement | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const citationsRef = useRef<HTMLDivElement>(null)
  const certPanel = useCertificationPanel()
  const { setWorkspaceMode, viewDocument, openDocumentUuid } = useWorkspace()

  // Resolve thinking content: streaming thinking > persisted thinking
  const thinkingText = streamingThinking || message.thinking || ''
  const duration = thinkingDuration ?? message.thinking_duration ?? null
  const hasThinking = thinkingText.length > 0

  const renderedHtml = useMemo(() => {
    if (isUser) return null
    // Strip any residual <think>/<thinking> blocks the backend didn't catch
    let cleaned = message.content.replace(/<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>\n?/g, '')
    // Replace [ACTION:type]label[/ACTION] markers with styled button HTML
    cleaned = cleaned.replace(ACTION_RE, (_match, type: string, label: string) =>
      `<button data-action="${type}" class="chat-action-btn">${label}</button>`
    )
    return DOMPurify.sanitize(marked.parse(cleaned) as string, {
      ADD_TAGS: ['button'],
      ADD_ATTR: ['data-action'],
    })
  }, [message.content, isUser])

  // Attach click handlers to action buttons after render
  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    const buttons = el.querySelectorAll<HTMLButtonElement>('[data-action]')
    const handlers: Array<[HTMLButtonElement, () => void]> = []
    buttons.forEach(btn => {
      const action = btn.getAttribute('data-action')
      const handler = () => {
        if (action === 'start-cert') certPanel.openPanel()
        else if (action === 'upload-docs') setWorkspaceMode('files')
      }
      btn.addEventListener('click', handler)
      handlers.push([btn, handler])
    })
    return () => { handlers.forEach(([b, h]) => b.removeEventListener('click', h)) }
  }, [renderedHtml, certPanel, setWorkspaceMode])

  const handleFeedback = async (rating: 'up' | 'down') => {
    setFeedback(rating)
    try {
      await submitChatFeedback({
        conversation_uuid: conversationUuid,
        message_index: messageIndex,
        rating,
      })
    } catch { /* ignore */ }
    // Invite a comment for BOTH sentiments — positive feedback is worth capturing,
    // not just complaints. The prompt copy flips with the rating below.
    if (!commentSent) setShowComment(true)
  }

  const handleSubmitComment = async () => {
    if (!comment.trim() || !feedback) return
    try {
      await submitChatFeedback({
        conversation_uuid: conversationUuid,
        message_index: messageIndex,
        rating: feedback,
        comment: comment.trim(),
      })
      setCommentSent(true)
      setShowComment(false)
    } catch { /* ignore */ }
  }

  // Close the citation chooser on an outside click or Escape, so it never
  // strands itself over the next message.
  useEffect(() => {
    if (citationMenu === null) return
    const onPointerDown = (e: MouseEvent) => {
      if (!citationsRef.current?.contains(e.target as Node)) setCitationMenu(null)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCitationMenu(null)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [citationMenu])

  useEffect(() => {
    if (citationMenu === null) {
      setMenuAlign('left')
      return
    }
    const menu = menuRef.current
    const pill = menu?.parentElement
    if (!menu || !pill) return
    const container = clippingAncestor(menu)
    const bounds = container?.getBoundingClientRect()
    const left = bounds?.left ?? 0
    const right = bounds?.right ?? document.documentElement.clientWidth
    const pillRect = pill.getBoundingClientRect()
    setMenuAlign(menuAlignmentFor(
      pillRect.left, pillRect.right, menu.offsetWidth, left, right,
    ))
  }, [citationMenu])

  const toggleCitationPreview = (index: number) => {
    setCitationMenu(null)
    setOpenCitation(prev => (prev === index ? null : index))
  }

  // The menu's "Preview" item is a destination, not a switch: picking it must
  // show the preview whether or not one is already open. Toggling belongs to
  // the pill itself, where a second click reads as "put it away".
  const showCitationPreview = (index: number) => {
    setCitationMenu(null)
    setOpenCitation(index)
  }

  // Open the cited document in the file viewer, landing on the passage the
  // chunk came from. Page numbers are a retrieval heuristic and can be wrong —
  // which is the whole reason to open the document — so the passage text is
  // the primary target and the page only breaks ties between matches.
  const openCitedDocument = (citation: Citation) => {
    if (!citation.document_uuid) return
    setCitationMenu(null)
    // The file panel is collapsed to nothing while chat has the workspace;
    // switch modes first or the document opens where nobody can see it.
    setWorkspaceMode('files')
    const anchor = citationAnchor(citation.content_preview)
    viewDocument(citation.document_uuid, citation.document_title, {
      terms: anchor ? [anchor] : [],
      page: citation.page ?? null,
      // Same reason as the extraction path: the chip says "p. ~N" for an
      // interpolated page, so the viewer's fallback must not drop the hedge.
      pageApproximate: citation.page_approximate ?? false,
    })
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

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
                      marginTop: 6,
                      padding: '10px 12px',
                      backgroundColor: '#f9fafb',
                      borderLeft: '3px solid var(--highlight-color, #eab308)',
                      borderRadius: 4,
                      fontSize: 13,
                      lineHeight: 1.6,
                      color: '#6b7280',
                      fontStyle: 'italic',
                      maxHeight: 400,
                      overflowY: 'auto',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                    className="hide-scrollbar"
                  >
                    {thinkingText}
                  </div>
                </div>
              </div>
            </div>
          )}

          {message.content && (
            <div
              ref={contentRef}
              className="select-text chat-markdown"
              style={{ fontSize: 14, lineHeight: 1.6 }}
              dangerouslySetInnerHTML={{ __html: renderedHtml! }}
            />
          )}

          {message.citations && message.citations.length > 0 && (() => {
            const open = openCitation !== null ? message.citations[openCitation] : null
            const openPreview = open?.content_preview?.trim() || ''
            return (
              <div style={{ marginTop: 8 }} ref={citationsRef}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  <span style={{ fontSize: 11, color: '#6b7280', alignSelf: 'center', marginRight: 2 }}>
                    Sources:
                  </span>
                  {message.citations.map((c, i) => {
                    const locator = formatPageLocator(c.page, c.page_approximate) ?? (c.sheet || null)
                    const label = locator ? `${c.document_title} · ${locator}` : c.document_title
                    const preview = c.content_preview || ''
                    const isOpen = openCitation === i
                    const menuOpen = citationMenu === i
                    // Only offer the chooser while there is somewhere to go:
                    // a source with no readable document behind it, or one
                    // already sitting in the viewer, goes straight to preview.
                    const offersOpen = !!c.document_uuid && c.document_uuid !== openDocumentUuid
                    const active = isOpen || menuOpen
                    return (
                      <span
                        key={`${c.chunk_id ?? c.document_id ?? i}`}
                        style={{ position: 'relative', display: 'inline-flex' }}
                      >
                        <button
                          type="button"
                          title={preview}
                          aria-haspopup={offersOpen ? 'menu' : undefined}
                          aria-expanded={offersOpen ? menuOpen : isOpen}
                          onClick={() => offersOpen
                            ? setCitationMenu(menuOpen ? null : i)
                            : toggleCitationPreview(i)}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            padding: '2px 8px', fontSize: 11, fontWeight: 500,
                            backgroundColor: active ? '#e0e7ff' : '#f3f4f6',
                            color: active ? '#3730a3' : '#374151',
                            border: `1px solid ${active ? '#c7d2fe' : '#e5e7eb'}`,
                            borderRadius: 999,
                            cursor: 'pointer', transition: 'all 0.15s',
                          }}
                        >
                          {label}
                        </button>
                        {menuOpen && (
                          <div
                            role="menu"
                            ref={menuRef}
                            aria-label={`Source: ${label}`}
                            style={{
                              position: 'absolute', top: 'calc(100% + 4px)',
                              ...(menuAlign === 'right' ? { right: 0 } : { left: 0 }),
                              zIndex: 30, minWidth: 150, padding: 4,
                              backgroundColor: '#fff', border: '1px solid #e5e7eb',
                              borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                            }}
                          >
                            <CitationMenuItem
                              icon={<Eye size={12} />}
                              label="Preview"
                              onClick={() => showCitationPreview(i)}
                            />
                            <CitationMenuItem
                              icon={<FileText size={12} />}
                              label={typeof c.page === 'number' ? `Open at p. ${c.page}` : 'Open document'}
                              onClick={() => openCitedDocument(c)}
                            />
                          </div>
                        )}
                      </span>
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
                      {(() => {
                        const loc = formatPageLocator(open.page, open.page_approximate) ?? open.sheet
                        return loc ? ` · ${loc}` : ''
                      })()}
                    </div>
                    {openPreview || 'No preview available for this source.'}
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

          {/* Comment form — shown after either thumbs-up or thumbs-down */}
          {!isStreamingProp && showComment && !commentSent && (
            <div style={{
              marginTop: 8, display: 'flex', gap: 8, alignItems: 'flex-start',
            }}>
              <input
                autoFocus
                value={comment}
                onChange={e => setComment(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSubmitComment() }}
                placeholder={feedback === 'up' ? 'What worked well? (optional)' : 'What went wrong? (optional)'}
                aria-label={feedback === 'up' ? 'What worked well? (optional)' : 'What went wrong? (optional)'}
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
