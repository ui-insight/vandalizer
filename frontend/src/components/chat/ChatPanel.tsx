import { useEffect, useRef, useState, useCallback } from 'react'
import { Loader2, BookOpen, X, ArrowDown, ChevronRight } from 'lucide-react'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { AttachmentList } from './AttachmentList'
import { useChat } from '../../hooks/useChat'
import { useOnboarding } from '../../hooks/useOnboarding'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { addLink, addDocument, removeDocument, removeLink } from '../../api/chat'
import { getUserConfig, updateUserConfig } from '../../api/config'
import type { FileAttachment, UrlAttachment } from '../../types/chat'

const LOADING_WORDS = [
  'Thinking', 'Vandalizing', 'Pondering', 'Analyzing',
  'Processing', 'Brewing', 'Crunching', 'Conjuring',
]

function StreamingLabel() {
  const [index, setIndex] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setIndex(i => (i + 1) % LOADING_WORDS.length)
        setFade(true)
      }, 200)
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  return (
    <span style={{
      opacity: fade ? 1 : 0,
      transition: 'opacity 0.2s ease',
      fontSize: 13,
      color: '#9ca3af',
    }}>
      {LOADING_WORDS[index]}&hellip;
    </span>
  )
}

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
    thinkingDuration,
    isStreaming,
    activityId,
    conversationUuid,
    error,
    send,
    loadHistory,
    setActivity,
  } = useChat()

  const { bumpActivitySignal, processingDoc, selectedDocUuids, selectedFolderUuids, activeKBUuid, activeKBTitle, deactivateKB } = useWorkspace()
  const { toast } = useToast()
  const { pills: onboardingPills, loading: onboardingLoading } = useOnboarding()
  const [fileAttachments, setFileAttachments] = useState<FileAttachment[]>([])
  const [urlAttachments, setUrlAttachments] = useState<UrlAttachment[]>([])
  const [attachLoading, setAttachLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const lastLoadedConvo = useRef<string | null>(null)
  const prevStreamingRef = useRef(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const prevScrollInfo = useRef({ scrollHeight: 0, scrollTop: 0, clientHeight: 0 })


  // Load saved model preference on mount
  useEffect(() => {
    getUserConfig().then(cfg => {
      if (cfg.model) {
        setSelectedModel(cfg.model)
      } else if (cfg.available_models?.length) {
        const first = cfg.available_models[0].tag || cfg.available_models[0].name
        setSelectedModel(first)
        updateUserConfig({ model: first }).catch(() => {})
      }
    }).catch(() => {})
  }, [])

  const handleModelChange = (model: string) => {
    setSelectedModel(model)
    updateUserConfig({ model }).catch(() => {})
  }

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    prevScrollInfo.current = {
      scrollHeight: el.scrollHeight,
      scrollTop: el.scrollTop,
      clientHeight: el.clientHeight,
    }
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollDown(distFromBottom > 80)
  }, [])

  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distFromBottom > 80) {
      setShowScrollDown(true)
    }
  }, [messages, streamingContent])

  const prevConvoRef = useRef(conversationUuid)
  useEffect(() => {
    if (conversationUuid !== prevConvoRef.current) {
      prevConvoRef.current = conversationUuid
      prevScrollInfo.current = { scrollHeight: 0, scrollTop: 0, clientHeight: 0 }
      setShowScrollDown(false)
    }
  }, [conversationUuid])

  const prevMsgCount = useRef(messages.length)
  useEffect(() => {
    if (messages.length > prevMsgCount.current) {
      const lastMsg = messages[messages.length - 1]
      if (lastMsg?.role === 'user') {
        prevScrollInfo.current = { scrollHeight: 0, scrollTop: 0, clientHeight: 0 }
        setShowScrollDown(false)
        const el = scrollContainerRef.current
        if (el) el.scrollTop = el.scrollHeight
      }
    }
    prevMsgCount.current = messages.length
  }, [messages])

  const scrollToBottom = useCallback(() => {
    setShowScrollDown(false)
    const el = scrollContainerRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (isStreaming !== prevStreamingRef.current) {
      prevStreamingRef.current = isStreaming
      bumpActivitySignal()
    }
  }, [isStreaming, bumpActivitySignal])

  useEffect(() => {
    if (conversationToLoad && conversationToLoad !== lastLoadedConvo.current) {
      lastLoadedConvo.current = conversationToLoad
      loadHistory(conversationToLoad).then(() => {
        setTimeout(() => {
          const el = scrollContainerRef.current
          if (el) el.scrollTop = el.scrollHeight
        }, 50)
      })
    }
  }, [conversationToLoad, loadHistory])

  const pendingHandled = useRef<string | null>(null)
  useEffect(() => {
    if (pendingMessage && pendingMessage !== pendingHandled.current && !isStreaming) {
      pendingHandled.current = pendingMessage
      send(pendingMessage, selectedDocUuids, undefined, undefined, undefined, selectedFolderUuids)
      onPendingMessageConsumed?.()
    }
  }, [pendingMessage, isStreaming, send, onPendingMessageConsumed])

  const hasDocContext = fileAttachments.length > 0 || urlAttachments.length > 0 || selectedDocUuids.length > 0 || selectedFolderUuids.length > 0

  const handleSend = (message: string, includeOnboardingContext?: boolean) => {
    send(message, selectedDocUuids, selectedModel || undefined, activeKBUuid || undefined, includeOnboardingContext, selectedFolderUuids)
  }


  const handleAttachFile = async (files: File[]) => {
    setAttachLoading(true)
    try {
      const result = await addDocument(files, activityId)
      if (result.attachments) {
        setFileAttachments((prev) => [...prev, ...result.attachments])
      }
      if (result.activity_id && result.conversation_uuid) {
        setActivity(result.activity_id, result.conversation_uuid)
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to attach file', 'error')
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
      if (result.activity_id && result.conversation_uuid) {
        setActivity(result.activity_id, result.conversation_uuid)
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to add website', 'error')
    } finally {
      setAttachLoading(false)
    }
  }

  const handleRemoveFile = async (id: string) => {
    try {
      await removeDocument(id)
      setFileAttachments((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to remove file', 'error')
    }
  }

  const handleRemoveUrl = async (id: string) => {
    try {
      await removeLink(id)
      setUrlAttachments((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to remove link', 'error')
    }
  }

  const handleExport = (format: string) => {
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
        onRemoveUrl={handleRemoveUrl}
      />

      {attachLoading && (
        <div className="flex items-center gap-2 border-b border-gray-200 bg-[color-mix(in_srgb,var(--highlight-color),white_90%)] px-4 py-2 text-xs text-highlight">
          <div className="chat-loader" style={{ width: 30 }} />
          Processing document... This may take a moment for PDFs and scanned files.
        </div>
      )}

      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto hide-scrollbar"
        style={{ padding: '20px 20px 180px 20px', position: 'relative' }}
      >
        {/* Empty state: banner + contextual pills */}
        {messages.length === 0 && !isStreaming && !onboardingLoading && (
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
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
                  {processingDoc ? (
                    <Loader2 className="h-7 w-7 opacity-90 animate-spin" />
                  ) : activeKBUuid ? (
                    <BookOpen className="h-7 w-7 opacity-90" />
                  ) : (
                    <img src="/images/joevandal.png" alt="Joe Vandal" style={{ width: 22, height: 35 }} className="opacity-90" />
                  )}
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>
                    {processingDoc
                      ? processingDoc.status === 'layout' ? 'Converting & Preparing Your Document...'
                        : processingDoc.status === 'ocr' ? 'Extracting Text From Your Document...'
                        : processingDoc.status === 'security' ? 'Scanning Your Document...'
                        : processingDoc.status === 'readying' ? 'Almost Ready...'
                        : 'Processing Your Document...'
                      : activeKBUuid
                        ? `Knowledge Base: ${activeKBTitle}`
                        : hasDocContext
                          ? 'Documents ready for analysis'
                          : 'What would you like to work on?'}
                  </div>
                  <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2, fontWeight: 400 }}>
                    {processingDoc
                      ? processingDoc.status === 'layout' ? "We're converting your document so it can be read and analyzed accurately."
                        : processingDoc.status === 'ocr' ? 'Running OCR to extract text content from your document.'
                        : processingDoc.status === 'security' ? "Checking for any sensitive information in your document."
                        : processingDoc.status === 'readying' ? 'Indexing your document for search and analysis.'
                        : 'Please wait while we prepare your document.'
                      : activeKBUuid
                        ? 'Ask questions grounded in your indexed documents and sources.'
                        : hasDocContext
                          ? 'Summarize, extract data, compare, or ask anything about your selected documents.'
                          : 'Select documents to analyze, activate a knowledge base, or ask me anything.'}
                  </div>
                </div>
              </div>
              {processingDoc && (
                <div className="relative z-[1]" style={{ marginTop: 16, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.2)', overflow: 'hidden' }}>
                  <div
                    className="animate-pulse"
                    style={{
                      height: '100%', borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.7)',
                      width: processingDoc.status === 'layout' ? '20%'
                        : processingDoc.status === 'ocr' ? '45%'
                        : processingDoc.status === 'security' ? '65%'
                        : processingDoc.status === 'readying' ? '85%'
                        : '10%',
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
              )}
            </div>

            {!processingDoc && (
              <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {(activeKBUuid ? [
                  'Summarize the key points across all sources',
                  'What are the most important facts and figures?',
                  'List every topic covered',
                ] : hasDocContext ? [
                  'Summarize this in 5 bullet points',
                  'Extract all names, dates, and numbers',
                  'List every action item and deadline',
                ] : onboardingPills).map(suggestion => (
                  <button
                    key={suggestion}
                    onClick={() => handleSend(suggestion, !activeKBUuid && !hasDocContext)}
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
            )}
          </div>
        )}

        {/* Chat messages */}
        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            message={msg}
            messageIndex={i}
            conversationUuid={conversationUuid || undefined}
          />
        ))}

        {/* Streaming: thinking-only phase */}
        {isStreaming && thinkingContent && !streamingContent && (
          <ChatMessage
            message={{ role: 'assistant', content: '' }}
            streamingThinking={thinkingContent}
            isStreaming
          />
        )}

        {/* Streaming: text phase */}
        {isStreaming && streamingContent && (
          <ChatMessage
            message={{ role: 'assistant', content: streamingContent }}
            streamingThinking={thinkingContent || undefined}
            thinkingDuration={thinkingDuration}
            isStreaming
          />
        )}

        {/* Loading indicator */}
        {isStreaming && !streamingContent && !thinkingContent && (
          <div style={{ padding: 15, marginBottom: 15, backgroundColor: '#00000008', borderRadius: 'var(--ui-radius, 12px)' }}>
            <div className="thinking-shimmer" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#9ca3af' }}>
              <ChevronRight size={14} />
              <StreamingLabel />
            </div>
          </div>
        )}

        {error && (
          <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
        )}

      </div>

      {/* Scroll to bottom button */}
      {showScrollDown && (
        <div style={{ display: 'flex', justifyContent: 'center', position: 'relative' }}>
          <button
            onClick={scrollToBottom}
            style={{
              position: 'absolute',
              bottom: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 36,
              height: 36,
              borderRadius: '50%',
              border: '1px solid #d1d5db',
              backgroundColor: '#fff',
              color: '#374151',
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
              zIndex: 10,
              transition: 'background-color 0.15s, box-shadow 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.backgroundColor = '#f3f4f6'
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.18)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.backgroundColor = '#fff'
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.12)'
            }}
            aria-label="Scroll to bottom"
          >
            <ArrowDown size={18} />
          </button>
        </div>
      )}



      {/* KB active badge */}
      {activeKBUuid && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 16px',
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--highlight-color, #eab308)',
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
            borderTop: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, white)',
          }}
        >
          <BookOpen size={14} />
          <span style={{ flex: 1 }}>Knowledge Base: {activeKBTitle}</span>
          <button
            onClick={deactivateKB}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              color: 'inherit',
              opacity: 0.7,
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onAttachFile={handleAttachFile}
        onAttachLink={handleAttachLink}
        disabled={isStreaming}
        selectedModel={selectedModel}
        onModelChange={handleModelChange}
        onExport={handleExport}
        hasMessages={messages.length > 0}
        hasDocuments={fileAttachments.length > 0 || urlAttachments.length > 0 || selectedDocUuids.length > 0 || selectedFolderUuids.length > 0}
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
