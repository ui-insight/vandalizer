import { useEffect, useRef, useState } from 'react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

interface PanelResizerProps {
  containerRef: React.RefObject<HTMLDivElement | null>
  value: number
  min: number
  max: number
  onDragStart?: () => void
  onDragEnd?: () => void
}

export function PanelResizer({ containerRef, value, min, max, onDragStart, onDragEnd }: PanelResizerProps) {
  const { setPanelSplit } = useWorkspace()
  const [dragging, setDragging] = useState(false)
  const restoreRef = useRef<(() => void) | null>(null)
  useEffect(() => () => { restoreRef.current?.() }, [])
  const clamp = (next: number) => Math.max(min, Math.min(max, next))
  const position = (clientX: number) => {
    const rect = containerRef.current?.getBoundingClientRect()
    return rect && rect.width > 6 ? clamp((clientX - rect.left) / (rect.width - 6) * 100) : value
  }
  const finish = () => {
    restoreRef.current?.(); restoreRef.current = null
    setDragging(false)
  }
  return (
    <div role="separator" tabIndex={0} aria-label="Resize workspace panels" aria-orientation="vertical"
      aria-controls="workspace-source-pane"
      aria-valuemin={Math.round(min * 10) / 10} aria-valuemax={Math.round(max * 10) / 10} aria-valuenow={Math.round(value * 10) / 10}
      aria-valuetext={`Left panel ${Math.round(value)} percent; tools ${Math.round(100 - value)} percent`}
      aria-describedby="workspace-resize-help"
      className="workspace-panel-resizer shrink-0 cursor-col-resize focus-visible:outline-2 focus-visible:outline-highlight"
      style={{ width: 6, position: 'relative', zIndex: 12, touchAction: 'none', background: dragging ? 'var(--highlight-color)' : '#e5e7eb' }}
      onKeyDown={event => {
        const next = event.key === 'ArrowLeft' ? value - 5 : event.key === 'ArrowRight' ? value + 5 : event.key === 'Home' ? min : event.key === 'End' ? max : null
        if (next !== null) { event.preventDefault(); setPanelSplit(clamp(next)) }
      }}
      onDoubleClick={() => setPanelSplit(clamp(60))}
      onPointerDown={event => {
        if (event.button !== 0 || !containerRef.current) return
        event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId)
        const { userSelect, cursor } = document.body.style
        restoreRef.current = () => { document.body.style.userSelect = userSelect; document.body.style.cursor = cursor; onDragEnd?.() }
        document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize'
        setDragging(true); onDragStart?.()
      }}
      onPointerMove={event => { if (dragging) setPanelSplit(position(event.clientX), true) }}
      onPointerUp={event => { if (dragging) { setPanelSplit(position(event.clientX)); finish(); event.currentTarget.releasePointerCapture(event.pointerId) } }}
      onPointerCancel={() => { if (dragging) { setPanelSplit(clamp(value)); finish() } }}
      onLostPointerCapture={() => { if (restoreRef.current) { setPanelSplit(clamp(value)); finish() } }}
    >
      <span aria-hidden="true" style={{ position: 'absolute', inset: '0 -4px' }} />
      <span id="workspace-resize-help" className="sr-only">Use Left and Right arrows to resize. Home and End use the smallest and largest sizes that fit. Double-click to reset.</span>
    </div>
  )
}
