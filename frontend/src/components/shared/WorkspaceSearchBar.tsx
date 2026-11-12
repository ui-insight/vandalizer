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
  return (
    <div className="workspace-search-bar">
      <Search size={16} aria-hidden="true" />
      <input
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
        <button type="button" aria-label="Clear search" onClick={() => onChange('')}>
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
