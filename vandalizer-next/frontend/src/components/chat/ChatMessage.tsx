import { useMemo, useState } from 'react'
import { ThumbsUp, ThumbsDown, Copy, Check } from 'lucide-react'
import { marked } from 'marked'
import { submitChatFeedback } from '../../api/feedback'
import type { ChatMessage as ChatMessageType } from '../../types/chat'

marked.setOptions({ breaks: true, gfm: true })

interface Props {
  message: ChatMessageType
  messageIndex?: number
  conversationUuid?: string
}

export function ChatMessage({ message, messageIndex, conversationUuid }: Props) {
  const isUser = message.role === 'user'
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null)
  const [copied, setCopied] = useState(false)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState('')
  const [commentSent, setCommentSent] = useState(false)

  const renderedHtml = useMemo(() => {
    if (isUser) return null
    return marked.parse(message.content) as string
  }, [message.content, isUser])

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
          <div
            className="select-text chat-markdown"
            style={{ fontSize: 14, lineHeight: 1.6 }}
            dangerouslySetInnerHTML={{ __html: renderedHtml! }}
          />

          {/* Feedback bar */}
          <div style={{
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
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>

          {/* Comment form for negative feedback */}
          {showComment && !commentSent && (
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
