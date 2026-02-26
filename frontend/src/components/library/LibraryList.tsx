import { BookOpen, Users } from 'lucide-react'
import type { Library } from '../../types/library'
import { cn } from '../../lib/cn'

interface Props {
  libraries: Library[]
  selectedId: string | null
  onSelect: (library: Library) => void
}

export function LibraryList({ libraries, selectedId, onSelect }: Props) {
  const personal = libraries.filter(l => l.scope === 'personal')
  const team = libraries.filter(l => l.scope === 'team')

  return (
    <div className="w-64 border-r border-gray-200 bg-white overflow-auto">
      {personal.length > 0 && (
        <div className="p-3">
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Personal</div>
          {personal.map(lib => (
            <button
              key={lib.id}
              onClick={() => onSelect(lib)}
              className={cn(
                'flex items-center gap-2 w-full px-3 py-2 rounded-md text-sm text-left transition-colors',
                selectedId === lib.id
                  ? 'bg-[color-mix(in_srgb,var(--highlight-color),white_85%)] text-gray-900'
                  : 'text-gray-700 hover:bg-gray-100',
              )}
            >
              <BookOpen className="h-4 w-4 shrink-0" />
              <div className="min-w-0">
                <div className="truncate font-medium">{lib.title}</div>
                <div className="text-xs text-gray-400">{lib.item_count} items</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {team.length > 0 && (
        <div className="p-3 border-t border-gray-100">
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Team</div>
          {team.map(lib => (
            <button
              key={lib.id}
              onClick={() => onSelect(lib)}
              className={cn(
                'flex items-center gap-2 w-full px-3 py-2 rounded-md text-sm text-left transition-colors',
                selectedId === lib.id
                  ? 'bg-[color-mix(in_srgb,var(--highlight-color),white_85%)] text-gray-900'
                  : 'text-gray-700 hover:bg-gray-100',
              )}
            >
              <Users className="h-4 w-4 shrink-0" />
              <div className="min-w-0">
                <div className="truncate font-medium">{lib.title}</div>
                <div className="text-xs text-gray-400">{lib.item_count} items</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
