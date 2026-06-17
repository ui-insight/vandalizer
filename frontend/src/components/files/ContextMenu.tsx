import { useEffect, useRef, useState, useLayoutEffect } from 'react'
import { Download, Edit2, Trash2, Copy, Users, FolderInput, FolderDown, MessageSquareText, Play, Library } from 'lucide-react'

interface ContextMenuProps {
  x: number
  y: number
  onClose: () => void
  onAskFolder?: () => void
  onRunWorkflow?: () => void
  onAddToKB?: () => void
  onRename?: () => void
  onMove?: () => void
  onDelete?: () => void
  onDownload?: () => void
  onExport?: () => void
  onCopyUuid?: () => void
  onConvertToTeam?: () => void
}

export function ContextMenu({
  x,
  y,
  onClose,
  onAskFolder,
  onRunWorkflow,
  onAddToKB,
  onRename,
  onMove,
  onDelete,
  onDownload,
  onExport,
  onCopyUuid,
  onConvertToTeam,
}: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ top: y, left: x })

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const pad = 8
    setPos({
      top: y + rect.height + pad > window.innerHeight ? Math.max(pad, y - rect.height) : y,
      left: x + rect.width + pad > window.innerWidth ? Math.max(pad, x - rect.width) : x,
    })
  }, [x, y])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const items = [
    onAskFolder && { label: 'Ask about folder', icon: MessageSquareText, action: onAskFolder },
    onRunWorkflow && { label: 'Run workflow on folder', icon: Play, action: onRunWorkflow },
    onAddToKB && { label: 'Add to knowledge base', icon: Library, action: onAddToKB },
    onRename && { label: 'Rename', icon: Edit2, action: onRename },
    onMove && { label: 'Move to…', icon: FolderInput, action: onMove },
    onExport && { label: 'Export contents', icon: FolderDown, action: onExport },
    onDownload && { label: 'Download', icon: Download, action: onDownload },
    onCopyUuid && { label: 'Copy UUID', icon: Copy, action: onCopyUuid },
    onConvertToTeam && { label: 'Convert to team folder', icon: Users, action: onConvertToTeam },
    onDelete && { label: 'Delete', icon: Trash2, action: onDelete, danger: true },
  ].filter(Boolean) as Array<{
    label: string
    icon: typeof Edit2
    action: () => void
    danger?: boolean
  }>

  return (
    <div
      ref={ref}
      role="menu"
      style={{
        top: pos.top,
        left: pos.left,
        borderColor: 'rgba(0,0,0,.15)',
        boxShadow: '0 8px 24px rgba(0,0,0,.12)',
      }}
      className="fixed z-[1000] min-w-[160px] rounded-lg border bg-white p-1.5"
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
    >
      {items.map((item) => (
        <button
          key={item.label}
          role="menuitem"
          onClick={() => {
            item.action()
            onClose()
          }}
          className={`flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left transition-colors ${
            item.danger
              ? 'text-red-600 hover:bg-red-50'
              : 'text-[#111] hover:bg-black/[.04]'
          }`}
        >
          <item.icon className="h-4 w-4" style={{ width: 18 }} />
          {item.label}
        </button>
      ))}
    </div>
  )
}
