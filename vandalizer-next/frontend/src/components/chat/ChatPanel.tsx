import { useEffect, useRef, useState } from 'react'
import { FileInput } from 'lucide-react'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { AttachmentList } from './AttachmentList'
import { useChat } from '../../hooks/useChat'
import { addLink, addDocument, removeDocument } from '../../api/chat'
import type { FileAttachment, UrlAttachment } from '../../types/chat'

interface ChatPanelProps {
  conversationToLoad?: string | null
  pendingMessage?: string | null
  onPendingMessageConsumed?: () => void
}

export function ChatPanel({ conversationToLoad, pendingMessage, onPendingMessageConsumed }: ChatPanelProps) {
  const {
    messages,
    streamingContent,
    thinkingContent,
    isStreaming,
    activityId,
    error,
    send,
    loadHistory,
  } = useChat()

  const [fileAttachments, setFileAttachments] = useState<FileAttachment[]>([])
  const [urlAttachments, setUrlAttachments] = useState<UrlAttachment[]>([])
  const [attachLoading, setAttachLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const lastLoadedConvo = useRef<string | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  // Load conversation history when requested from workspace context
  useEffect(() => {
    if (conversationToLoad && conversationToLoad !== lastLoadedConvo.current) {
      lastLoadedConvo.current = conversationToLoad
      loadHistory(conversationToLoad)
    }
  }, [conversationToLoad, loadHistory])

  // Send a pending message injected from outside (e.g. library prompt click)
  const pendingHandled = useRef<string | null>(null)
  useEffect(() => {
    if (pendingMessage && pendingMessage !== pendingHandled.current && !isStreaming) {
      pendingHandled.current = pendingMessage
      send(pendingMessage, [])
      onPendingMessageConsumed?.()
    }
  }, [pendingMessage, isStreaming, send, onPendingMessageConsumed])

  const handleSend = (message: string) => {
    send(message, [], selectedModel || undefined)
  }

  const handleAttachFile = async (files: File[]) => {
    setAttachLoading(true)
    try {
      const result = await addDocument(files, activityId)
      if (result.attachments) {
        setFileAttachments((prev) => [...prev, ...result.attachments])
      }
    } catch {
      // Error handling
    } finally {
      setAttachLoading(false)
    }
  }

  const handleAttachLink = async (url: string) => {
    setAttachLoading(true)
    try {
      const result = await addLink(url, activityId)
      setUrlAttachments((prev) => [
        ...prev,
        {
          id: result.attachment_id,
          url,
          title: result.title,
          created_at: new Date().toISOString(),
        },
      ])
    } catch {
      // Error handling
    } finally {
      setAttachLoading(false)
    }
  }

  const handleRemoveFile = async (id: string) => {
    try {
      await removeDocument(id)
      setFileAttachments((prev) => prev.filter((a) => a.id !== id))
    } catch {
      // Error handling
    }
  }

  const handleExport = (format: string) => {
    // Build conversation text
    const text = messages
      .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}:\n${m.content}`)
      .join('\n\n---\n\n')
    if (format === 'text') {
      const blob = new Blob([text], { type: 'text/plain' })
      downloadBlob(blob, 'conversation.txt')
    } else if (format === 'csv') {
      const rows = [['Role', 'Content']]
      messages.forEach(m => rows.push([m.role, m.content.replace(/"/g, '""')]))
      const csv = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n')
      const blob = new Blob([csv], { type: 'text/csv' })
      downloadBlob(blob, 'conversation.csv')
    } else if (format === 'pdf') {
      // For PDF, generate a simple HTML and open print dialog
      const html = `<html><head><title>Conversation</title><style>body{font-family:sans-serif;padding:40px;max-width:800px;margin:0 auto}
      .msg{margin-bottom:20px;padding:12px;border-radius:8px}.user{background:#f3f4f6;border-left:4px solid #eab308}
      .assistant{background:#fafafa}.role{font-weight:bold;margin-bottom:4px;font-size:12px;text-transform:uppercase;color:#666}</style></head>
      <body>${messages.map(m => `<div class="msg ${m.role}"><div class="role">${m.role}</div><div>${m.content.replace(/\n/g, '<br>')}</div></div>`).join('')}</body></html>`
      const win = window.open('', '_blank')
      if (win) { win.document.write(html); win.document.close(); win.print() }
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Attachments bar */}
      <AttachmentList
        fileAttachments={fileAttachments}
        urlAttachments={urlAttachments}
        onRemoveFile={handleRemoveFile}
      />

      {attachLoading && (
        <div className="flex items-center gap-2 border-b border-gray-200 bg-[color-mix(in_srgb,var(--highlight-color),white_90%)] px-4 py-2 text-xs text-highlight">
          <div className="chat-loader" style={{ width: 30 }} />
          Attaching...
        </div>
      )}

      {/* Messages area */}
      <div
        className="flex-1 overflow-y-auto hide-scrollbar"
        style={{ padding: '20px 20px 180px 20px' }}
      >
        {/* Empty state: gradient helper box + recommendations */}
        {messages.length === 0 && !isStreaming && (
          <>
            <div
              className="relative overflow-hidden text-white"
              style={{
                padding: '28px 24px',
                borderRadius: 'var(--ui-radius, 12px)',
                background: 'linear-gradient(135deg, var(--highlight-complement, #6a11cb), color-mix(in srgb, var(--highlight-color, #f1b300) 70%, #ffffff 30%))',
                transition: 'filter 0.3s ease',
              }}
            >
              <div
                style={{
                  position: 'absolute', top: '-50%', left: '-50%',
                  width: '200%', height: '200%',
                  background: 'radial-gradient(circle at center, rgba(255,255,255,0.15), transparent 70%)',
                  animation: 'rotateBG 32s linear infinite',
                }}
              />
              <div className="relative z-[1] flex items-center gap-4">
                <div style={{ animation: 'float 3s ease-in-out infinite' }} className="shrink-0">
                  <FileInput className="h-7 w-7 opacity-90" />
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>
                    Ready to get started?
                  </div>
                  <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2, fontWeight: 400 }}>
                    Add or select a document to begin.
                  </div>
                </div>
              </div>
            </div>

            {/* Recommendation chips */}
            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {[
                'Summarize this document',
                'What are the key findings?',
                'Extract important dates and names',
                'List the main topics covered',
              ].map(suggestion => (
                <button
                  key={suggestion}
                  onClick={() => handleSend(suggestion)}
                  style={{
                    padding: '8px 14px',
                    fontSize: 13,
                    fontWeight: 500,
                    fontFamily: 'inherit',
                    border: '1px solid #e5e7eb',
                    borderRadius: 20,
                    backgroundColor: '#fff',
                    color: '#374151',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
                    e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = '#e5e7eb'
                    e.currentTarget.style.backgroundColor = '#fff'
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </>
        )}

        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}

        {/* Streaming content */}
        {isStreaming && streamingContent && (
          <ChatMessage message={{ role: 'assistant', content: streamingContent }} />
        )}

        {/* Thinking indicator */}
        {isStreaming && thinkingContent && (
          <div className="flex items-center gap-2 py-2 text-xs text-gray-400">
            <div className="chat-loader" style={{ width: 30 }} />
            <span className="italic">Thinking...</span>
          </div>
        )}

        {/* Loading indicator */}
        {isStreaming && !streamingContent && !thinkingContent && (
          <div style={{ padding: 15, marginBottom: 15, backgroundColor: '#00000008', borderRadius: 'var(--ui-radius, 12px)' }}>
            <div className="chat-loader" />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onAttachFile={handleAttachFile}
        onAttachLink={handleAttachLink}
        disabled={isStreaming}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onExport={handleExport}
        hasMessages={messages.length > 0}
      />
    </div>
  )
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
