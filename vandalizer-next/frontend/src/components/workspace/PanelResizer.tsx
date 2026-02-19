import { useCallback, useRef, useState } from 'react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function PanelResizer() {
  const { setPanelSplit } = useWorkspace()
  const [dragging, setDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setDragging(true)

      const parentEl = (e.target as HTMLElement).parentElement
      if (!parentEl) return

      const onMove = (moveE: MouseEvent) => {
        const rect = parentEl.getBoundingClientRect()
        const pct = ((moveE.clientX - rect.left) / rect.width) * 100
        setPanelSplit(pct)
      }

      const onUp = () => {
        setDragging(false)
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [setPanelSplit],
  )

  return (
    <div
      ref={containerRef}
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
