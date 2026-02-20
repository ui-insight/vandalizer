import { useCallback, useRef, useState } from 'react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function PanelResizer() {
  const { setPanelSplit } = useWorkspace()
  const [dragging, setDragging] = useState(false)
  const rafRef = useRef(0)

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setDragging(true)

      const parentEl = (e.target as HTMLElement).parentElement
      if (!parentEl) return

      // Disable text selection while dragging
      document.body.style.userSelect = 'none'
      document.body.style.cursor = 'col-resize'

      const onMove = (moveE: MouseEvent) => {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = requestAnimationFrame(() => {
          const rect = parentEl.getBoundingClientRect()
          const pct = ((moveE.clientX - rect.left) / rect.width) * 100
          setPanelSplit(pct, true)
        })
      }

      const onUp = (upE: MouseEvent) => {
        cancelAnimationFrame(rafRef.current)
        setDragging(false)
        document.body.style.userSelect = ''
        document.body.style.cursor = ''
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        // Persist final position to localStorage
        const rect = parentEl.getBoundingClientRect()
        const pct = ((upE.clientX - rect.left) / rect.width) * 100
        setPanelSplit(pct, false)
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [setPanelSplit],
  )

  return (
    <div
      onMouseDown={handleMouseDown}
      className="shrink-0 cursor-col-resize"
      style={{
        width: 4,
        background: dragging ? '#999' : '#d8d8d8',
        transition: 'background 0.2s ease',
        zIndex: 600,
      }}
    />
  )
}
