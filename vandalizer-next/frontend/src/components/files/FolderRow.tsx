import { Folder as FolderIcon, MoreVertical } from 'lucide-react'
import type { Folder } from '../../types/document'

interface FolderRowProps {
  folder: Folder
  onClick: () => void
  onContextMenu: (e: React.MouseEvent) => void
}

export function FolderRow({ folder, onClick, onContextMenu }: FolderRowProps) {
  // Team folders get teal color, personal folders get gray
  const iconColor = folder.is_shared_team_root ? 'rgb(0, 128, 128)' : 'rgb(162, 162, 162)'

  return (
    <tr
      className="cursor-pointer"
      onClick={onClick}
      onContextMenu={onContextMenu}
      style={{ borderBottom: '1px solid #dddddd' }}
    >
      <td style={{ padding: '12px 15px' }}>
        <div className="flex items-center">
          <FolderIcon className="h-4 w-4 shrink-0" style={{ color: iconColor }} />
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
