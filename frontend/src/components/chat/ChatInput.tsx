import { useState, useRef, useEffect, useCallback, useId, type KeyboardEvent, type ReactNode } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { Send, Square, X, Plus, FileUp, Globe, BookOpen, Download, ChevronDown, Cpu } from 'lucide-react'
import { getModels } from '../../api/config'
import type { ModelInfo } from '../../types/workflow'
import { ModelEffortPicker } from '../ModelEffortPicker'
import { useBranding } from '../../contexts/BrandingContext'
import { useUploadPolicy } from '../../hooks/useUploadPolicy'

interface Props {
  onSend: (message: string) => void | Promise<void>
  onAttachFile?: (files: File[]) => void
  onAttachLink?: (url: string) => void
  // Opens the knowledge base screen so the user can pick a KB to chat with.
  onAddKnowledge?: () => void
  disabled?: boolean
  sendDisabled?: boolean
  isStreaming?: boolean
  onStop?: () => void
  selectedModel?: string
  onModelChange?: (model: string) => void
  onModelsLoaded?: (models: ModelInfo[]) => void
  onExport?: (format: string) => void
  hasMessages?: boolean
  hasDocuments?: boolean
  contextMeter?: ReactNode
  memoryControl?: ReactNode
  // Bumped by the workspace to pull focus into the composer (e.g. the file
  // browser's "Ask about folder" action).
  focusSignal?: number
}

const MIN_COMPOSER_TEXT_HEIGHT = 24

export function ChatInput({
  onSend, onAttachFile, onAttachLink, onAddKnowledge, disabled, sendDisabled,
  isStreaming, onStop,
  selectedModel, onModelChange, onModelsLoaded, onExport, hasMessages, hasDocuments,
  contextMeter, memoryControl, focusSignal,
}: Props) {
  const branding = useBranding()
  const uploadPolicy = useUploadPolicy()
  const [message, setMessage] = useState('')
  const [showAddMenu, setShowAddMenu] = useState(false)
  const [showLinkInput, setShowLinkInput] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const [showModelMenu, setShowModelMenu] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [modelError, setModelError] = useState(false)
  const [modelsLoading, setModelsLoading] = useState(true)
  const [sendError, setSendError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const sending = useRef(false)
  const modelRequest = useRef(0)
  const helpId = useId()
  const onModelsLoadedRef = useRef(onModelsLoaded)
  onModelsLoadedRef.current = onModelsLoaded
  const fileInputRef = useRef<HTMLInputElement>(null)
  const addMenuRef = useRef<HTMLDivElement>(null)
  const modelMenuRef = useRef<HTMLDivElement>(null)
  const exportMenuRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-grow the textarea to fit its content, capped by max-height (CSS).
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    // A zero scrollHeight can occur briefly while the workspace is laying out
    // (and in a few browser/zoom combinations). Never let that collapse the
    // empty composer and hide its placeholder.
    ta.style.height = `${Math.max(ta.scrollHeight, MIN_COMPOSER_TEXT_HEIGHT)}px`
  }, [message])

  // Pull focus into the composer when the workspace requests it. Guard on the
  // initial 0 so the chat doesn't grab focus on first mount.
  useEffect(() => {
    if (focusSignal) textareaRef.current?.focus()
  }, [focusSignal])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (addMenuRef.current && !addMenuRef.current.contains(target)) setShowAddMenu(false)
      if (exportMenuRef.current && !exportMenuRef.current.contains(target)) setShowExportMenu(false)
    }
    // Use 'click' instead of 'mousedown' so the handler fires AFTER React
    // onClick on dropdown items, avoiding event-ordering conflicts.
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [])

  const loadModels = useCallback(async () => {
    const request = ++modelRequest.current
    setModelsLoading(true)
    setModelError(false)
    try {
      const result = await getModels()
      if (request !== modelRequest.current) return
      setModels(result)
      onModelsLoadedRef.current?.(result)
    } catch {
      if (request === modelRequest.current) setModelError(true)
    } finally {
      if (request === modelRequest.current) setModelsLoading(false)
    }
  }, [])
  const cancelModelRead = useCallback(() => { modelRequest.current++ }, [])
  useEffect(() => { void loadModels(); return cancelModelRead }, [loadModels, cancelModelRead])

  const handleSend = async () => {
    const trimmed = message.trim()
    if (!trimmed || disabled || sendDisabled || sending.current) return
    sending.current = true
    setSubmitting(true)
    setSendError(null)
    try {
      await onSend(trimmed)
      // A new draft typed during submission belongs to the next message.
      setMessage(current => current === message ? '' : current)
    } catch (reason) {
      setSendError(reason instanceof Error ? reason.message : 'Could not send.')
    } finally {
      sending.current = false
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) onAttachFile?.(files)
    e.target.value = ''
  }

  const handleLinkSubmit = () => {
    if (linkUrl.trim()) {
      onAttachLink?.(linkUrl.trim())
      setLinkUrl('')
      setShowLinkInput(false)
    }
  }

  // Deduplicate models by tag
  const uniqueModels = models.filter((m, i, arr) => arr.findIndex(x => x.tag === m.tag) === i)

  const displayModel = selectedModel
    ? (uniqueModels.find(m => m.tag === selectedModel)?.tag || selectedModel)
    : null

  return (
    <div
      className="shrink-0 p-[15px] bg-white"
      style={{ boxShadow: '0 0px 23px -8px rgb(211, 211, 211)', zIndex: 500 }}
    >
      {/* Link input row */}
      {showLinkInput && (
        <div className="mb-3 flex gap-2">
          <input
            type="url"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            placeholder="Enter URL..."
            aria-label="Enter URL"
            className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none focus:ring-2 focus:ring-highlight-on-light"
            onKeyDown={(e) => e.key === 'Enter' && handleLinkSubmit()}
          />
          <button
            onClick={handleLinkSubmit}
            className="rounded-[var(--ui-radius)] bg-highlight px-3 py-1.5 text-sm text-highlight-text font-bold hover:brightness-90"
          >
            Add
          </button>
          <button
            onClick={() => setShowLinkInput(false)}
            className="rounded-md px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700"
          >
            Cancel
          </button>
        </div>
      )}

      {submitting && isStreaming && <p role="status" className="mb-2 text-sm text-gray-700">Queueing message…</p>}
      {sendError && <p role="alert" className="mb-2 text-sm text-red-800">{sendError} Your draft is kept; try again.</p>}
      <p id={helpId} className="sr-only">{isStreaming ? 'Enter queues your message for the current conversation.' : 'Enter sends your message.'} Shift+Enter adds a new line.</p>
      {/* Ask question container */}
      <div
        className="flex flex-col rounded-[var(--ui-radius)] p-2.5 focus-within:ring-2 focus-within:ring-highlight-on-light"
        style={{ backgroundColor: '#19191913' }}
      >
        {/* Text input area */}
        <div
          className="cursor-text"
          style={{ padding: '8px 6px 12px 6px' }}
          onClick={() => textareaRef.current?.focus()}
        >
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              hasDocuments
                ? 'Ask about these documents…'
                : `Ask ${branding.appName}…`
            }
            aria-label="Message input"
            aria-describedby={helpId}
            rows={1}
            wrap="soft"
            className="block min-w-0 w-full resize-none overflow-x-hidden overflow-y-auto border-0 bg-transparent text-base font-medium caret-highlight placeholder:text-[#626a75] placeholder:font-medium focus:outline-none focus-visible:outline-none"
            style={{ fontSize: 16, lineHeight: 1.5, minHeight: `${MIN_COMPOSER_TEXT_HEIGHT}px`, maxHeight: '25vh' }}
            disabled={disabled}
          />
        </div>

        {/* Controls toolbar — min-w-0 lets children shrink instead of overflowing on narrow screens */}
        <div className="flex min-w-0 flex-wrap items-center gap-1.5 pt-1 px-1">
          {/* + Add button */}
          <div ref={addMenuRef} className="relative">
            <button
              onClick={() => setShowAddMenu(!showAddMenu)}
              aria-expanded={showAddMenu}
              aria-haspopup="menu"
              className="flex items-center gap-1 rounded-[30px] border border-gray-300 px-2.5 py-1 text-xs font-medium text-[#555] hover:bg-gray-100 transition-all"
            >
              <Plus className="h-3.5 w-3.5" />
              Add
              <ChevronDown className="h-3 w-3" />
            </button>

            {showAddMenu && (
              <div
                role="menu"
                className="absolute left-0 z-[1000] min-w-[220px] rounded-[var(--ui-radius)] border bg-white p-1.5"
                style={{ bottom: 'calc(100% + 8px)', borderColor: 'rgba(0,0,0,0.14)', boxShadow: '0 10px 28px rgba(0,0,0,0.16)' }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setShowAddMenu(false)
                }}
              >
                <button
                  role="menuitem"
                  onClick={() => { fileInputRef.current?.click(); setShowAddMenu(false) }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm text-left text-[#1f2937] hover:bg-black/[.04] transition-colors"
                  style={{ minHeight: 40 }}
                >
                  <FileUp className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                  <span>Add Document<span style={{ display: 'block', fontSize: 12, color: '#58616d', lineHeight: 1.5 }}>{uploadPolicy.description}</span></span>
                </button>
                <button
                  role="menuitem"
                  onClick={() => { setShowLinkInput(true); setShowAddMenu(false) }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm text-left text-[#1f2937] hover:bg-black/[.04] transition-colors"
                  style={{ minHeight: 40 }}
                >
                  <Globe className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                  <span>Add Website</span>
                </button>
                {onAddKnowledge && (
                  <button
                    role="menuitem"
                    onClick={() => { onAddKnowledge(); setShowAddMenu(false) }}
                    className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm text-left text-[#1f2937] hover:bg-black/[.04] transition-colors"
                    style={{ minHeight: 40 }}
                  >
                    <BookOpen className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                    <span>Add Knowledge Base</span>
                  </button>
                )}
              </div>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            aria-label="Attach files"
            accept={uploadPolicy.accept}
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Model selector */}
          {onModelChange && (
            <div ref={modelMenuRef} className="relative">
              <button
                onClick={() => setShowModelMenu(!showModelMenu)}
                aria-expanded={showModelMenu}
                aria-haspopup="dialog"
                aria-label={`Choose chat model: ${displayModel || 'default'}`}
                className="flex min-w-0 items-center gap-1 rounded-[30px] border border-gray-300 px-2.5 py-1 text-xs font-medium text-[#555] hover:bg-gray-100 transition-all"
              >
                <Cpu className="h-3 w-3 shrink-0" />
                <span className="truncate max-w-[28vw] sm:max-w-[160px]">{displayModel || 'Model'}</span>
                <ChevronDown className="h-3 w-3 shrink-0" />
              </button>

              {showModelMenu && (
                <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/20 p-4" onClick={e => { if (e.target === e.currentTarget) setShowModelMenu(false) }}>
                  <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, tabbableOptions: { displayCheck: 'none' } }}>
                    <div role="dialog" aria-modal="true" aria-label="Choose chat model" className="w-full max-w-md overflow-y-auto rounded-xl border border-gray-300 bg-white p-3 shadow-xl" style={{ maxHeight: 'calc(100dvh - 32px)' }} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setShowModelMenu(false) } }}>
                      <div className="mb-2 flex items-center justify-between gap-3"><h2 className="text-base font-semibold text-gray-900">Choose chat model</h2><button type="button" aria-label="Close model picker" className="rounded p-2 text-gray-700" onClick={() => setShowModelMenu(false)}><X size={18} /></button></div>
                      {modelsLoading ? <p role="status" className="p-3 text-sm text-gray-700">Loading models…</p>
                        : modelError ? <div role="alert" className="p-3 text-sm text-red-800">Could not load available models. <button type="button" className="underline" onClick={() => void loadModels()}>Retry models</button></div>
                        : uniqueModels.length === 0 ? <p className="p-3 text-sm text-gray-700">No models are currently available. Contact your administrator or <button type="button" className="underline" onClick={() => void loadModels()}>Refresh models</button>.</p>
                        : <ModelEffortPicker models={uniqueModels} selectedModel={selectedModel ?? ''} onChange={tag => { onModelChange(tag); setShowModelMenu(false) }} />}
                    </div>
                  </FocusTrap>
                </div>
              )}
            </div>
          )}

          {/* Context meter */}
          {contextMeter}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Assistant memory */}
          {memoryControl}

          {/* Export button */}
          {onExport && hasMessages && (
            <div ref={exportMenuRef} className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                type="button"
                className="flex items-center justify-center rounded-[var(--ui-radius)] p-1.5 text-gray-500 hover:text-gray-600 transition-colors"
                aria-label="Export conversation"
                aria-expanded={showExportMenu}
                aria-haspopup="menu"
              >
                <Download className="h-4 w-4" />
              </button>

              {showExportMenu && (
                <div
                  role="menu"
                  aria-label="Export conversation format"
                  className="absolute right-0 z-[1000] min-w-[140px] rounded-[var(--ui-radius)] border bg-white p-1.5"
                  style={{ bottom: 'calc(100% + 8px)', borderColor: 'rgba(0,0,0,0.14)', boxShadow: '0 10px 28px rgba(0,0,0,0.16)' }}
                  onKeyDown={(e) => { if (e.key === 'Escape') setShowExportMenu(false) }}
                >
                  {['PDF', 'CSV', 'Text'].map(fmt => (
                    <button
                      key={fmt}
                      role="menuitem"
                      onClick={() => { onExport(fmt.toLowerCase()); setShowExportMenu(false) }}
                      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-left text-[#1f2937] hover:bg-black/[.04] transition-colors"
                    >
                      <Download className="h-3.5 w-3.5 shrink-0 text-gray-500" />
                      {fmt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* A queued message is also available to touch users while Stop stays reachable. */}
          {isStreaming && onStop && message.trim() && <button type="button" onClick={() => void handleSend()} disabled={disabled || sendDisabled || submitting} aria-label="Queue message" title="Queue message" className="shrink-0 rounded border border-gray-400 bg-white p-2 text-xs text-gray-800 disabled:opacity-50">Queue</button>}
          {/* Send / Stop button */}
          {isStreaming && onStop ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop response"
              title="Stop"
              className="flex shrink-0 items-center justify-center rounded-[var(--ui-radius)] bg-highlight p-1.5 text-highlight-text transition-opacity"
            >
              <Square className="h-4 w-4 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={!message.trim() || disabled || sendDisabled || submitting}
              aria-label="Send message"
              className="flex shrink-0 items-center justify-center rounded-[var(--ui-radius)] bg-highlight p-1.5 text-highlight-text transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
