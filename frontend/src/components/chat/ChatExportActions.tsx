import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Copy, Download } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import type { ChatMessage } from '../../types/chat'
import { exportChat } from '../../api/chat'
import { saveChatArtifact } from '../../api/artifacts'
import { conversationToCsv, conversationToText, copyMessages, exportMessages } from './conversationExport'
import { openPrintPage } from '../../lib/printPage'
import { announceWorkspaceWrite } from '../../lib/chatWrites'

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

const formats = [ ['html', 'HTML transcript'], ['docx', 'Word (.docx)'], ['xlsx', 'Excel (.xlsx)'], ['pdf', 'PDF'], ['csv', 'CSV'], ['text', 'Text'], ['artifact', 'Save transcript as page'] ] as const

export function ChatExportActions({ messages, scope = 'message', names = {}, disabled = false, artifactSource }: {
  messages: ChatMessage[]
  scope?: 'message' | 'conversation'
  names?: Record<string, string>
  artifactSource?: { project_uuid?: string; conversation_uuid?: string }
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const [savedArtifact, setSavedArtifact] = useState<string | null>(null)
  const artifactRequest = useRef<{ content: string; id: string } | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const running = useRef(false)
  const close = () => { setOpen(false); button.current?.focus() }
  useLayoutEffect(() => {
    if (!open || !button.current || !menu.current) return
    const rect = button.current.getBoundingClientRect()
    const height = menu.current.offsetHeight
    const width = menu.current.offsetWidth
    setPosition({
      left: Math.max(8, Math.min(window.innerWidth - width - 8, rect.right - width)),
      top: rect.top >= height + 8 ? rect.top - height - 8 : Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - height - 8)),
    })
    menu.current.querySelector('button')?.focus()
  }, [open])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !button.current?.contains(event.target as Node)) setOpen(false)
    }
    const dismiss = () => setOpen(false)
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', dismiss)
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', dismiss) }
  }, [open])
  const run = async (format: string) => {
    if (running.current || disabled) return
    running.current = true
    close()
    setBusy(true)
    setError('')
    try {
      if (format === 'artifact') {
        const normalized = exportMessages(messages, names)
        const content = JSON.stringify({ normalized, artifactSource })
        if (artifactRequest.current?.content !== content) artifactRequest.current = { content, id: crypto.randomUUID() }
        const artifact = await saveChatArtifact(normalized, artifactRequest.current.id, artifactSource)
        setSavedArtifact(artifact.uuid)
        announceWorkspaceWrite('pages')
      } else if (format === 'html' || format === 'docx' || format === 'xlsx') {
        download(await exportChat(format, exportMessages(messages, names)), `${scope}.${format}`)
      } else if (format === 'pdf') {
        const esc = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        const content = exportMessages(messages, names).map(m => `<section><h2>${m.role === 'user' ? 'User' : 'Assistant'}</h2>${DOMPurify.sanitize(marked.parse(m.content, { async: false }), { FORBID_TAGS: ['img', 'style', 'iframe'] })}<pre>${esc([...m.tools, m.evidence].join('\n\n'))}</pre></section>`).join('')
        openPrintPage(`<html><head><title>Chat export</title><style>body{font:14px/1.5 sans-serif;max-width:900px;margin:auto;padding:24px}section{margin-bottom:24px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px}</style></head><body>${content}</body></html>`)
      } else {
        download(new Blob([format === 'csv' ? conversationToCsv(messages, names) : conversationToText(messages, names)], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'text/plain;charset=utf-8' }), `${scope}.${format === 'csv' ? 'csv' : 'txt'}`)
      }
    } catch (err) {
      setError(err instanceof Error && err.name !== 'AbortError' ? err.message : 'Export timed out. Please try again.')
    } finally { running.current = false; setBusy(false) }
  }
  return <div className="relative flex flex-wrap items-center gap-1 text-inherit">
    <button type="button" className="rounded p-1.5 hover:bg-black/10 disabled:opacity-50" aria-label={`Copy ${scope}`} title={`Copy ${scope}`} disabled={disabled || busy} onClick={async () => {
      setError('')
      try {
        await navigator.clipboard.writeText(copyMessages(messages, names, scope === 'conversation'))
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch { setError('Could not copy. Select the text to copy it, or try again.') }
    }}>{copied ? <Check size={16} /> : <Copy size={16} />}</button>
    <button ref={button} type="button" className="rounded p-1.5 hover:bg-black/10 disabled:opacity-50" aria-label={`Export ${scope}`} title={`Export ${scope}`} aria-haspopup="menu" aria-expanded={open} disabled={disabled || busy} onClick={() => setOpen(!open)}><Download size={16} /></button>
    {busy && <span role="status" className="text-xs">Preparing export…</span>}
    {open && createPortal(<div ref={menu} role="menu" style={position} className="fixed z-[1000] w-[236px] max-h-[90vh] overflow-auto rounded-lg border bg-white p-1.5 text-gray-800 shadow-lg" aria-label={`Export ${scope} format`} onBlur={e => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false)
    }} onKeyDown={e => {
      if (e.key === 'Escape') { e.stopPropagation(); close() }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
        e.preventDefault()
        const items = Array.from(e.currentTarget.querySelectorAll('button'))
        const index = items.indexOf(document.activeElement as HTMLButtonElement)
        items[e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (index + (e.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length]?.focus()
      }
    }}>
      <div className="chat-export-heading"><strong>{scope === 'conversation' ? 'Export conversation' : 'Export message'}</strong><span>Text and source references</span></div>
      {formats.map(([format, label]) => <button key={format} type="button" role="menuitem" disabled={disabled} className={`block min-h-10 w-full rounded px-3 py-2 text-left text-sm hover:bg-gray-100 focus:bg-gray-100 disabled:opacity-50 ${format === 'artifact' ? 'mt-1 border-t border-slate-200 pt-3' : ''}`} onClick={() => void run(format)}>{label}</button>)}
    </div>, document.body)}
    {error && <p role="alert" className="w-full text-xs">{error}</p>}
    {savedArtifact && <a className="text-xs underline" href={`/pages/${savedArtifact}`} target="_blank" rel="noreferrer">Open saved page</a>}
  </div>
}
