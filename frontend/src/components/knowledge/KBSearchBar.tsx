import { useState, useEffect } from 'react'
import { Search, X } from 'lucide-react'

interface KBSearchBarProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

export function KBSearchBar({ value, onChange, placeholder = 'Search knowledge bases...' }: KBSearchBarProps) {
  const [draft, setDraft] = useState(value)

  // Debounce
  useEffect(() => {
    const t = setTimeout(() => onChange(draft), 300)
    return () => clearTimeout(t)
  }, [draft, onChange])

  // Sync external resets
  useEffect(() => { setDraft(value) }, [value])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
      padding: "0 var(--workspace-space-12)", margin: "var(--workspace-space-8) var(--workspace-space-12) var(--workspace-space-4)",
      backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
    }}>
      <Search size={13} style={{ color: 'var(--workspace-muted)', flexShrink: 0 }} aria-hidden="true" />
      <input
        type="search"
        aria-label={placeholder}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        placeholder={placeholder}
        onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 2px var(--highlight-color, #eab308)' }}
        onBlur={e => { e.currentTarget.style.boxShadow = 'none' }}
        style={{
          flex: 1, padding: '7px 0', fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit',
          color: 'var(--workspace-text)', backgroundColor: 'transparent',
          border: 'none', outline: 'none', borderRadius: 'var(--workspace-radius-small)',
        }}
      />
      {draft && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => { setDraft(''); onChange('') }}
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 'var(--workspace-space-2)', display: 'flex' }}
        >
          <X size={12} style={{ color: 'var(--workspace-muted)' }} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
