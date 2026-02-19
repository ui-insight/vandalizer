import { useMemo } from 'react'
import { marked } from 'marked'
import type { ChatMessage as ChatMessageType } from '../../types/chat'

marked.setOptions({ breaks: true, gfm: true })

interface Props {
  message: ChatMessageType
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  const renderedHtml = useMemo(() => {
    if (isUser) return null
    return marked.parse(message.content) as string
  }, [message.content, isUser])

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
        <div
          className="select-text chat-markdown"
          style={{ fontSize: 14, lineHeight: 1.6 }}
          dangerouslySetInnerHTML={{ __html: renderedHtml! }}
        />
      )}
    </div>
  )
}
