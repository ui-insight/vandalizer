import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'

interface BreadcrumbsProps {
  items: Array<{ uuid: string; title: string }>
  onNavigate: (folderId: string | null) => void
  // The home/floor the trail bottoms out at. null = global root. When set
  // (project scope), "Home" and "Up" land here instead of the global root.
  floor?: string | null
  homeLabel?: string
  // When set, the Up arrow, Home, and ancestor crumbs accept file rows
  // dragged from the list below, moving the file into that folder
  // ("0" = top level). This is the only drag path that moves a file *up*
  // the tree — folder rows only cover folders visible in the current view.
  onDropFile?: (fileUuid: string, folderId: string) => void
}

export function Breadcrumbs({ items, onNavigate, floor = null, homeLabel = 'Home', onDropFile }: BreadcrumbsProps) {
  const atRoot = items.length === 0
  const parentId = items.length >= 2 ? items[items.length - 2].uuid : floor
  const currentTitle = items.length > 0 ? items[items.length - 1].title : null
  const ancestors = items.slice(0, -1)
  const [dragOverTarget, setDragOverTarget] = useState<string | null>(null)

  const handleUp = () => {
    if (atRoot) return
    onNavigate(parentId)
  }

  // Shared drag & drop handlers for a crumb that maps to folder `folderId`.
  // `key` identifies which crumb to highlight (the Up arrow and Home can map
  // to the same folder without lighting up together).
  const dropTargetProps = (key: string, folderId: string) => {
    if (!onDropFile || atRoot) return {}
    return {
      onDragEnter: (e: React.DragEvent) => {
        e.preventDefault()
        setDragOverTarget(key)
      },
      onDragOver: (e: React.DragEvent) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
      },
      onDragLeave: () => {
        setDragOverTarget(prev => (prev === key ? null : prev))
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setDragOverTarget(null)
        const fileUuid = e.dataTransfer.getData('text/plain')
        if (fileUuid) onDropFile(fileUuid, folderId)
      },
    }
  }

  const dragOverStyle = (targetId: string): React.CSSProperties =>
    dragOverTarget === targetId
      ? {
          backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 15%, white)',
          outline: '2px solid color-mix(in srgb, var(--highlight-color, #eab308) 60%, white)',
          outlineOffset: '-2px',
          borderRadius: 6,
        }
      : {}

  const homeTargetId = floor ?? '0'
  const upTargetId = parentId ?? '0'

  return (
    <nav
      aria-label="Folder navigation"
      className="overflow-x-auto whitespace-nowrap flex items-center gap-2"
      style={{ padding: '20px 30px 0px 0px' }}
    >
      {!atRoot && (
        <button
          type="button"
          onClick={handleUp}
          aria-label="Go to parent folder"
          title="Go to parent folder"
          className="inline-flex items-center justify-center rounded-md border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          style={{ width: 28, height: 28, ...dragOverStyle('up') }}
          {...dropTargetProps('up', upTargetId)}
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      )}

      <ol className="inline-flex items-center gap-1 list-none m-0 p-0">
        <li className="inline-flex items-center text-sm">
          {atRoot ? (
            <span style={{ color: '#111', fontWeight: 600 }}>{homeLabel}</span>
          ) : (
            <button
              type="button"
              onClick={() => onNavigate(floor)}
              className="bg-transparent border-0 cursor-pointer text-gray-600 hover:text-gray-900 hover:underline"
              style={{ fontWeight: 400, padding: '2px 4px', margin: '-2px -4px', ...dragOverStyle('home') }}
              {...dropTargetProps('home', homeTargetId)}
            >
              {homeLabel}
            </button>
          )}
        </li>
        {ancestors.map((item) => (
          <li key={item.uuid} className="inline-flex items-center text-sm">
            <span className="mx-[7.5px] text-gray-400" aria-hidden="true">›</span>
            <button
              type="button"
              onClick={() => onNavigate(item.uuid)}
              className="bg-transparent border-0 cursor-pointer text-gray-600 hover:text-gray-900 hover:underline"
              style={{ fontWeight: 400, padding: '2px 4px', margin: '-2px -4px', ...dragOverStyle(item.uuid) }}
              {...dropTargetProps(item.uuid, item.uuid)}
            >
              {item.title}
            </button>
          </li>
        ))}
        {currentTitle && (
          <li className="inline-flex items-center text-sm" aria-current="page">
            <span className="mx-[7.5px] text-gray-400" aria-hidden="true">›</span>
            <span style={{ color: '#111', fontWeight: 600 }}>{currentTitle}</span>
          </li>
        )}
      </ol>
    </nav>
  )
}
