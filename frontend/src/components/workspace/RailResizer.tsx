import { useEffect, useRef, useState } from 'react'
import { ResizeGrip } from './PanelResizer'

interface RailResizerProps {
  /** Current Activity panel width in pixels. */
  value: number
  min: number
  max: number
  /** `commit` is false while dragging, true for the width to remember. */
  onChange: (width: number, commit: boolean) => void
  onReset: () => void
  onDragStart?: () => void
  onDragEnd?: () => void
}

/** The divider between the tools pane and the Activity panel. The panel is
 *  anchored to the right edge of the window, so its width is the distance
 *  from the pointer to that edge. */
export function RailResizer({ value, min, max, onChange, onReset, onDragStart, onDragEnd }: RailResizerProps) {
  const [dragging, setDragging] = useState(false)
  const restoreRef = useRef<(() => void) | null>(null)
  const startValue = useRef(value)
  const startX = useRef(0)
  const moved = useRef(false)
  useEffect(() => () => { restoreRef.current?.() }, [])
  const clamp = (next: number) => Math.round(Math.max(min, Math.min(max, next)))
  const widthAt = (clientX: number) => clamp(window.innerWidth - clientX)
  const finish = () => {
    restoreRef.current?.(); restoreRef.current = null
    setDragging(false)
  }
  return (
    <div role="separator" tabIndex={0} aria-label="Resize Activity panel" aria-orientation="vertical"
      aria-controls="workspace-activity-rail"
      aria-valuemin={min} aria-valuemax={max} aria-valuenow={value}
      aria-valuetext={`Activity panel ${value} pixels wide`}
      aria-describedby="activity-resize-help"
      title="Drag to resize. Double-click to reset."
      className="workspace-panel-resizer cursor-col-resize focus-visible:outline-2 focus-visible:outline-highlight"
      style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 6, zIndex: 12, touchAction: 'none', background: dragging ? 'var(--highlight-color)' : '#e5e7eb' }}
      onKeyDown={event => {
        // The panel grows leftwards, so Left widens it.
        const next = event.key === 'ArrowLeft' ? value + 20 : event.key === 'ArrowRight' ? value - 20 : event.key === 'Home' ? min : event.key === 'End' ? max : null
        if (next !== null) { event.preventDefault(); onChange(clamp(next), true) }
      }}
      onDoubleClick={onReset}
      onPointerDown={event => {
        if (event.button !== 0) return
        event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId)
        const { userSelect, cursor } = document.body.style
        restoreRef.current = () => { document.body.style.userSelect = userSelect; document.body.style.cursor = cursor; onDragEnd?.() }
        document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize'
        startValue.current = value
        startX.current = event.clientX
        moved.current = false
        setDragging(true); onDragStart?.()
      }}
      onPointerMove={event => {
        if (!dragging) return
        // A click to focus the divider is not a resize: nothing changes until
        // the pointer has actually travelled.
        if (!moved.current && Math.abs(event.clientX - startX.current) < 3) return
        moved.current = true
        onChange(widthAt(event.clientX), false)
      }}
      onPointerUp={event => {
        if (!dragging) return
        if (moved.current) onChange(widthAt(event.clientX), true)
        finish(); event.currentTarget.releasePointerCapture(event.pointerId)
      }}
      // An interrupted drag puts the panel back without saving anything: the
      // width shown may be the saved one fitted to a narrow window, and
      // saving that would overwrite the person's preference.
      onPointerCancel={() => { if (dragging) { if (moved.current) onChange(startValue.current, false); finish() } }}
      onLostPointerCapture={() => { if (restoreRef.current) { if (moved.current) onChange(startValue.current, false); finish() } }}
    >
      <span aria-hidden="true" style={{ position: 'absolute', inset: '0 -4px' }} />
      <ResizeGrip active={dragging} />
      <span id="activity-resize-help" className="sr-only">Use Left and Right arrows to resize. Home and End use the narrowest and widest sizes that fit. Double-click to reset.</span>
    </div>
  )
}
