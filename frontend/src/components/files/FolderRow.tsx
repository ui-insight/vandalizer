import { useState, useRef } from 'react'
import { Folder as FolderIcon, Users, MoreVertical, Eye } from 'lucide-react'
import type { Folder } from '../../types/document'

interface FolderRowProps {
  folder: Folder
  onClick: () => void
  onContextMenu: (e: React.MouseEvent) => void
  selected?: boolean
  onToggleSelect?: (uuid: string) => void
  onDropFile?: (fileUuid: string, folderUuid: string) => void
  isWatched?: boolean
}

export function FolderRow({ folder, onClick, onContextMenu, selected, onToggleSelect, onDropFile, isWatched }: FolderRowProps) {
  const isTeam = !!folder.team_id || folder.is_shared_team_root
  const iconColor = isTeam ? 'rgb(0, 128, 128)' : 'rgb(162, 162, 162)'
  const [isDragOver, setIsDragOver] = useState(false)
  const dragCounter = useRef(0)
  const justDropped = useRef(false)

  return (
    <tr
      className="cursor-pointer"
      tabIndex={0}
      role="row"
      aria-label={`Folder: ${folder.title}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      onClick={(e) => {
        if (justDropped.current) {
          justDropped.current = false
          return
        }
        if (e.button === 0) onClick()
      }}
      onContextMenu={(e) => {
        e.preventDefault()
        onContextMenu(e)
      }}
      onDragEnter={(e) => {
        e.preventDefault()
        dragCounter.current++
        setIsDragOver(true)
      }}
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
      }}
      onDragLeave={() => {
        dragCounter.current--
        if (dragCounter.current === 0) setIsDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        e.stopPropagation()
        dragCounter.current = 0
        setIsDragOver(false)
        justDropped.current = true
        const fileUuid = e.dataTransfer.getData('text/plain')
        if (fileUuid) onDropFile?.(fileUuid, folder.uuid)
      }}
      style={{
        borderBottom: '1px solid #dddddd',
        backgroundColor: isDragOver ? 'color-mix(in srgb, var(--highlight-color, #eab308) 15%, white)' : undefined,
        outline: isDragOver ? '2px solid color-mix(in srgb, var(--highlight-color, #eab308) 60%, white)' : undefined,
        outlineOffset: '-2px',
      }}
    >
      {/* Checkbox */}
      <td style={{ padding: '12px 0 12px 15px', width: 32 }}>
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect(folder.uuid)}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Select ${folder.title}`}
            className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
          />
        )}
      </td>

      {/* Name + icon */}
      <td style={{ padding: '12px 15px' }}>
        <div className="flex items-center min-w-0">
          {isTeam ? (
            <Users className="h-4 w-4 shrink-0" style={{ color: iconColor }} />
          ) : (
            <FolderIcon className="h-4 w-4 shrink-0" style={{ color: iconColor }} />
          )}
          <span
            style={{
              paddingRight: 10,
              paddingLeft: 5,
              fontWeight: 450,
              color: '#17181abb',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1,
              minWidth: 0,
            }}
          >
            {folder.title}
          </span>
          {isTeam && (
            <span className="shrink-0" style={{
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
              color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
              marginLeft: 6, whiteSpace: 'nowrap',
            }}>
              Team
            </span>
          )}
          {isWatched && (
            <span className="shrink-0" style={{
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
              color: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)',
              marginLeft: 6, whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: 2,
            }}>
              <Eye style={{ width: 9, height: 9 }} />
              Watched
            </span>
          )}
        </div>
      </td>

      {/* Modified (empty for folders) */}
      <td style={{ padding: '12px 15px' }} />

      {/* Menu */}
      <td style={{ padding: '12px 4px', width: 40 }}>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onContextMenu(e)
          }}
          className="bg-transparent border-0 cursor-pointer p-1 text-[#191919] hover:bg-black/5 rounded"
          aria-label="More options"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
      </td>
    </tr>
  )
}
