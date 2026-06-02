import { useEffect } from 'react'

/**
 * Keyboard navigation for the presenter deck. Clamps to [0, count-1] and tears
 * down its listener on unmount. Esc invokes onClose.
 */
export function usePresentNav({
  count,
  index,
  onIndex,
  onClose,
}: {
  count: number
  index: number
  onIndex: (i: number) => void
  onClose: () => void
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowRight':
        case ' ':
        case 'PageDown':
          e.preventDefault()
          onIndex(Math.min(count - 1, index + 1))
          break
        case 'ArrowLeft':
        case 'PageUp':
          e.preventDefault()
          onIndex(Math.max(0, index - 1))
          break
        case 'Home':
          e.preventDefault()
          onIndex(0)
          break
        case 'End':
          e.preventDefault()
          onIndex(count - 1)
          break
        case 'Escape':
          e.preventDefault()
          onClose()
          break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [count, index, onIndex, onClose])
}
