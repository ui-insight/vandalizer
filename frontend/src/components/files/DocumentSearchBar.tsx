import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef } from 'react'
import { ChevronUp, ChevronDown, X } from 'lucide-react'

interface Props {
  query: string
  onQueryChange: (q: string) => void
  currentMatch: number // 1-indexed; 0 if none
  totalMatches: number
  onPrev: () => void
  onNext: () => void
  onClose: () => void
  autoFocus?: boolean
}

export function DocumentSearchBar({
  query, onQueryChange, currentMatch, totalMatches,
  onPrev, onNext, onClose, autoFocus,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const close = () => { onClose(); if (triggerRef.current?.isConnected) triggerRef.current.focus() }

  useEffect(() => {
    if (autoFocus) {
      if (document.activeElement instanceof HTMLElement && document.activeElement !== inputRef.current) triggerRef.current = document.activeElement
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [autoFocus])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (e.shiftKey) onPrev()
      else onNext()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      close()
    }
  }

  const trimmed = query.trim()
  const status = trimmed === ''
    ? ''
    : totalMatches === 0 ? 'No results' : `${currentMatch} of ${totalMatches}`
  const statusColor = trimmed && totalMatches === 0 ? '#b91c1c' : '#6b7280'

  return (
    <div
      role="search"
      style={{
        position: 'absolute',
        top: 8,
        right: 12,
        zIndex: 200,
        display: 'flex',
        flexWrap: 'wrap',
        width: 420, maxWidth: 'calc(100% - 24px)',
        alignItems: 'center',
        gap: 'var(--workspace-space-2)',
        padding: "var(--workspace-space-4) var(--workspace-space-6)",
        borderRadius: 'var(--workspace-radius-medium)',
        border: "1px solid var(--workspace-border)",
        backgroundColor: 'rgba(255,255,255,0.97)',
        backdropFilter: 'blur(8px)',
        boxShadow: '0 2px 12px rgba(0,0,0,0.15)',
      }}
    >
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Find in document"
        aria-label="Find in document"
        onFocus={(e) => { e.currentTarget.style.boxShadow = '0 0 0 2px var(--highlight-color, #eab308)' }}
        onBlur={(e) => { e.currentTarget.style.boxShadow = 'none' }}
        style={{
          width: 200, flex: '1 1 180px', minWidth: 0,
          maxWidth: '100%',
          height: 28,
          padding: "0 var(--workspace-space-8)",
          fontSize: 'var(--workspace-font-control)',
          border: 'none',
          outline: 'none',
          background: 'transparent',
          color: '#111827',
          borderRadius: 'var(--workspace-radius-small)',
        }}
      />
      <span
        aria-live="polite"
        style={{
          minWidth: 70,
          textAlign: 'center',
          fontSize: 'var(--workspace-font-meta)',
          color: statusColor,
          padding: "0 var(--workspace-space-4)",
        }}
      >
        {status}
      </span>
      <button
        type="button"
        onClick={onPrev}
        disabled={totalMatches === 0}
        style={iconBtnStyle(totalMatches === 0)}
        title="Previous (Shift+Enter)"
        aria-label="Previous match"
      >
        <ChevronUp size={16} />
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={totalMatches === 0}
        style={iconBtnStyle(totalMatches === 0)}
        title="Next (Enter)"
        aria-label="Next match"
      >
        <ChevronDown size={16} />
      </button>
      <button
        type="button"
        onClick={close}
        style={iconBtnStyle(false)}
        title="Close (Esc)"
        aria-label="Close find"
      >
        <X size={16} />
      </button>
    </div>
  )
}

function iconBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 28,
    height: 28,
    borderRadius: 'var(--workspace-radius-small)',
    border: 'none',
    background: 'transparent',
    cursor: disabled ? 'default' : 'pointer',
    color: disabled ? '#d1d5db' : '#374151',
  }
}

// Window-level Cmd/Ctrl+F hook scoped to a viewer's root element. Activates
// only when the mouse is hovering the viewer or focus is inside it, so
// browser Find continues to work everywhere else on the page.
export function useFindInDocumentHotkey(
  rootRef: React.RefObject<HTMLElement | null>,
  isOpen: boolean,
  onOpen: () => void,
  onClose: () => void,
) {
  usePanelEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const root = rootRef.current
      if (!root) return
      const inScope =
        root.matches(':hover') || root.contains(document.activeElement)
      if (!inScope) return

      const modKey = e.metaKey || e.ctrlKey
      if (modKey && (e.key === 'f' || e.key === 'F')) {
        e.preventDefault()
        onOpen()
      } else if (e.key === 'Escape' && isOpen) {
        e.preventDefault()
        close()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [rootRef, isOpen, onOpen, onClose])
}
