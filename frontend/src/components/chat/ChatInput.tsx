import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Send, Plus, FileUp, Globe, Download, ChevronDown, Cpu } from 'lucide-react'
import { getModels } from '../../api/config'
import type { ModelInfo } from '../../types/workflow'
import { ModelEffortPicker, effortLabelForModel } from '../ModelEffortPicker'

interface Props {
  onSend: (message: string) => void
  onAttachFile?: (files: File[]) => void
  onAttachLink?: (url: string) => void
  disabled?: boolean
  selectedModel?: string
  onModelChange?: (model: string) => void
  onExport?: (format: string) => void
  hasMessages?: boolean
  hasDocuments?: boolean
}

export function ChatInput({
  onSend, onAttachFile, onAttachLink, disabled,
  selectedModel, onModelChange, onExport, hasMessages, hasDocuments,
}: Props) {
  const [message, setMessage] = useState('')
  const [showAddMenu, setShowAddMenu] = useState(false)
  const [showLinkInput, setShowLinkInput] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const [showModelMenu, setShowModelMenu] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [models, setModels] = useState<ModelInfo[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const addMenuRef = useRef<HTMLDivElement>(null)
  const modelMenuRef = useRef<HTMLDivElement>(null)
  const exportMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (addMenuRef.current && !addMenuRef.current.contains(target)) setShowAddMenu(false)
      if (modelMenuRef.current && !modelMenuRef.current.contains(target)) setShowModelMenu(false)
      if (exportMenuRef.current && !exportMenuRef.current.contains(target)) setShowExportMenu(false)
    }
    // Use 'click' instead of 'mousedown' so the handler fires AFTER React
    // onClick on dropdown items, avoiding event-ordering conflicts.
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [])

  // Fetch models eagerly so the button label resolves immediately
  useEffect(() => {
    if (models.length === 0) {
      getModels().then(setModels).catch(() => {})
    }
  }, [models.length])

  const handleSend = () => {
    const trimmed = message.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setMessage('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
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

  const effortLabel = uniqueModels.length > 0 && selectedModel
    ? effortLabelForModel(uniqueModels, selectedModel)
    : null
  const displayModel = effortLabel
    ? `${effortLabel} effort`
    : selectedModel
      ? (uniqueModels.find(m => m.tag === selectedModel)?.tag || selectedModel.split('/').pop() || selectedModel)
      : null

  return (
    <div
      className="p-[15px] bg-white"
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
            className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-highlight focus:outline-none"
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

      {/* Ask question container */}
      <div
        className="flex flex-col rounded-[var(--ui-radius)] p-2.5"
        style={{ backgroundColor: '#19191913' }}
      >
        {/* Text input area */}
        <div
          className="overflow-y-auto cursor-text"
          style={{ maxHeight: '25vh', padding: '8px 6px 12px 6px' }}
        >
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hasDocuments ? "Ask anything about this document..." : "Ask Vandalizer anything..."}
            aria-label="Message input"
            rows={1}
            className="w-full resize-none border-0 bg-transparent text-base font-medium placeholder:text-[#8a8f98] placeholder:font-medium focus:outline-none"
            style={{ fontSize: 16 }}
            disabled={disabled}
          />
        </div>

        {/* Controls toolbar */}
        <div className="flex items-center gap-2.5 pt-1 px-1">
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
                  <span>Add Document</span>
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
              </div>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Model selector */}
          {onModelChange && (
            <div ref={modelMenuRef} className="relative">
              <button
                onClick={() => setShowModelMenu(!showModelMenu)}
                aria-expanded={showModelMenu}
                aria-haspopup="true"
                className="flex items-center gap-1 rounded-[30px] border border-gray-300 px-2.5 py-1 text-xs font-medium text-[#555] hover:bg-gray-100 transition-all"
              >
                <Cpu className="h-3 w-3" />
                {displayModel || 'Model'}
                <ChevronDown className="h-3 w-3" />
              </button>

              {showModelMenu && (
                <div
                  role="dialog"
                  aria-label="Select model effort level"
                  className="absolute left-0 z-[1000] rounded-[var(--ui-radius)] border bg-white"
                  style={{ bottom: 'calc(100% + 8px)', width: 310, borderColor: 'rgba(0,0,0,0.14)', boxShadow: '0 10px 28px rgba(0,0,0,0.16)' }}
                  onKeyDown={(e) => { if (e.key === 'Escape') setShowModelMenu(false) }}
                >
                  <ModelEffortPicker
                    models={uniqueModels}
                    selectedModel={selectedModel ?? ''}
                    onChange={(tag) => { onModelChange(tag); setShowModelMenu(false) }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Export button */}
          {onExport && hasMessages && (
            <div ref={exportMenuRef} className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                className="flex items-center justify-center rounded-[var(--ui-radius)] p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
                aria-label="Export conversation"
                aria-expanded={showExportMenu}
                aria-haspopup="menu"
              >
                <Download className="h-4 w-4" />
              </button>

              {showExportMenu && (
                <div
                  className="absolute right-0 z-[1000] min-w-[140px] rounded-[var(--ui-radius)] border bg-white p-1.5"
                  style={{ bottom: 'calc(100% + 8px)', borderColor: 'rgba(0,0,0,0.14)', boxShadow: '0 10px 28px rgba(0,0,0,0.16)' }}
                >
                  {['PDF', 'CSV', 'Text'].map(fmt => (
                    <button
                      key={fmt}
                      onClick={() => { onExport(fmt.toLowerCase()); setShowExportMenu(false) }}
                      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-left text-[#1f2937] hover:bg-black/[.04] transition-colors"
                    >
                      <Download className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      {fmt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!message.trim() || disabled}
            aria-label="Send message"
            className="flex items-center justify-center rounded-[var(--ui-radius)] bg-highlight p-1.5 text-highlight-text transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
