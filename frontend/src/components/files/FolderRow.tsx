import { Folder as FolderIcon, Users, MoreVertical } from 'lucide-react'
import type { Folder } from '../../types/document'

interface FolderRowProps {
  folder: Folder
  onClick: () => void
  onContextMenu: (e: React.MouseEvent) => void
  selected?: boolean
  onToggleSelect?: (uuid: string) => void
}

export function FolderRow({ folder, onClick, onContextMenu, selected, onToggleSelect }: FolderRowProps) {
  const isTeam = !!folder.team_id || folder.is_shared_team_root
  const iconColor = isTeam ? 'rgb(0, 128, 128)' : 'rgb(162, 162, 162)'

  return (
    <tr
      className="cursor-pointer"
      onClick={onClick}
      onContextMenu={onContextMenu}
      style={{ borderBottom: '1px solid #dddddd' }}
    >
      {onToggleSelect && (
        <td style={{ padding: '12px 0 12px 15px', width: 32 }}>
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect(folder.uuid)}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
          />
        </td>
      )}
      <td style={{ padding: '12px 15px' }}>
        <div className="flex items-center">
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
            }}
          >
            {folder.title}
          </span>
          {isTeam && (
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
              color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
              marginLeft: 6, whiteSpace: 'nowrap',
            }}>
              Team
            </span>
          )}

          <button
            onClick={(e) => {
              e.stopPropagation()
              onContextMenu(e)
            }}
            className="ml-auto bg-transparent border-0 cursor-pointer p-1 text-[#191919] hover:bg-black/5 rounded"
            style={{ float: 'right' }}
          >
            <MoreVertical className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  )
}
