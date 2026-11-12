import { useRef } from 'react'
import { Search, X } from 'lucide-react'

/**
 * The one search box for workspace panels (Files, Library): a grey bar that
 * is always visible, with a comfortable maximum width so it doesn't stretch
 * or shrink with the panel as the divider is dragged.
 */
export function WorkspaceSearchBar({ value, onChange, label, placeholder }: {
  value: string
  onChange: (value: string) => void
  /** Accessible name, e.g. "Search library". */
  label: string
  placeholder: string
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <div className="workspace-search-bar">
      <Search size={16} aria-hidden="true" />
      <input
        ref={input}
        type="search"
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={event => onChange(event.target.value)}
        onKeyDown={event => {
          // Escape clears a search in progress; with nothing typed it is left
          // for the panel (closing a dialog, leaving a field).
          if (event.key === 'Escape' && value) {
            event.stopPropagation()
            onChange('')
          }
        }}
      />
      {value && (
        // The button goes away once the box is empty, so hand focus back to
        // the box: ready to type again, and never lost to the page.
        <button type="button" aria-label="Clear search" onClick={() => { onChange(''); input.current?.focus() }}>
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
