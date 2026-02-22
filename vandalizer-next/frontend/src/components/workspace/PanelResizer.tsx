import { useCallback, useRef, useState } from 'react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

interface PanelResizerProps {
  containerRef: React.RefObject<HTMLDivElement | null>
  onDragStart?: () => void
  onDragEnd?: () => void
}

export function PanelResizer({ containerRef, onDragStart, onDragEnd }: PanelResizerProps) {
  const { setPanelSplit } = useWorkspace()
  const [dragging, setDragging] = useState(false)
  const [hovering, setHovering] = useState(false)
  const rafRef = useRef(0)

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setDragging(true)
      onDragStart?.()

      const container = containerRef.current
      if (!container) return

      // Disable text selection while dragging
      document.body.style.userSelect = 'none'
      document.body.style.cursor = 'col-resize'

      const onMove = (moveE: MouseEvent) => {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = requestAnimationFrame(() => {
          const rect = container.getBoundingClientRect()
          const pct = ((moveE.clientX - rect.left) / rect.width) * 100
          setPanelSplit(pct, true)
        })
      }

      const onUp = (upE: MouseEvent) => {
        cancelAnimationFrame(rafRef.current)
        setDragging(false)
        onDragEnd?.()
        document.body.style.userSelect = ''
        document.body.style.cursor = ''
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        // Persist final position to localStorage
        const rect = container.getBoundingClientRect()
        const pct = ((upE.clientX - rect.left) / rect.width) * 100
        setPanelSplit(pct, false)
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [containerRef, setPanelSplit, onDragStart, onDragEnd],
  )

  const active = dragging || hovering

  return (
    <div
      onMouseDown={handleMouseDown}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      className="shrink-0 cursor-col-resize"
      style={{
        width: 1,
        position: 'relative',
        zIndex: 600,
      }}
    >
      {/* Visible line */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: active ? 3 : 1,
          background: active ? 'var(--highlight-color, #eab308)' : '#d8d8d8',
          transition: 'width 0.15s ease, background 0.15s ease',
        }}
      />
      {/* Wider invisible hit area */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: -5,
          width: 11,
        }}
      />
    </div>
  )
}
