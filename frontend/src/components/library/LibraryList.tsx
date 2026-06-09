import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpen, Users } from 'lucide-react'
import type { Library } from '../../types/library'
import { cn } from '../../lib/cn'

interface Props {
  libraries: Library[]
  selectedId: string | null
  onSelect: (library: Library) => void
}

const WIDTH_STORAGE_KEY = 'library.sidebarWidth'
const DEFAULT_WIDTH = 256
const MIN_WIDTH = 180
const MAX_WIDTH = 560

function readStoredWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_WIDTH
  const raw = window.localStorage.getItem(WIDTH_STORAGE_KEY)
  const parsed = raw ? Number.parseInt(raw, 10) : NaN
  if (!Number.isFinite(parsed)) return DEFAULT_WIDTH
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, parsed))
}

export function LibraryList({ libraries, selectedId, onSelect }: Props) {
  const personal = libraries.filter(l => l.scope === 'personal')
  const team = libraries.filter(l => l.scope === 'team')

  const [width, setWidth] = useState<number>(() => readStoredWidth())
  const [dragging, setDragging] = useState(false)
  const [hovering, setHovering] = useState(false)
  const rafRef = useRef(0)

  useEffect(() => {
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setDragging(true)

    const startX = e.clientX
    const startWidth = width

    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'

    const onMove = (moveE: MouseEvent) => {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + (moveE.clientX - startX)))
        setWidth(next)
      })
    }

    const onUp = () => {
      cancelAnimationFrame(rafRef.current)
      setDragging(false)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [width])

  useEffect(() => {
    if (dragging) return
    try {
      window.localStorage.setItem(WIDTH_STORAGE_KEY, String(width))
    } catch {
      // Storage unavailable — silently ignore.
    }
  }, [width, dragging])

  const handleDoubleClick = useCallback(() => {
    setWidth(DEFAULT_WIDTH)
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setWidth(w => Math.max(MIN_WIDTH, w - (e.shiftKey ? 32 : 8)))
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      setWidth(w => Math.min(MAX_WIDTH, w + (e.shiftKey ? 32 : 8)))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setWidth(MIN_WIDTH)
    } else if (e.key === 'End') {
      e.preventDefault()
      setWidth(MAX_WIDTH)
    }
  }, [])

  const handleActive = dragging || hovering

  return (
    <div
      className="relative shrink-0 bg-white border-r border-gray-200"
      style={{ width }}
    >
      <div className="h-full overflow-auto">
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

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuenow={width}
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={MAX_WIDTH}
        tabIndex={0}
        onMouseDown={handleMouseDown}
        onDoubleClick={handleDoubleClick}
        onKeyDown={handleKeyDown}
        onMouseEnter={() => setHovering(true)}
        onMouseLeave={() => setHovering(false)}
        className="absolute top-0 bottom-0 cursor-col-resize select-none focus:outline-none"
        style={{ right: -5, width: 11, zIndex: 10 }}
      >
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: 5,
            width: handleActive ? 3 : 1,
            background: handleActive ? 'var(--highlight-color, #eab308)' : 'transparent',
            transition: 'width 0.15s ease, background 0.15s ease',
          }}
        />
      </div>
    </div>
  )
}
