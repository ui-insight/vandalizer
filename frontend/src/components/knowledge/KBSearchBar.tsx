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
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '0 12px', margin: '8px 12px 4px',
      backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
    }}>
      <Search size={13} style={{ color: '#666', flexShrink: 0 }} />
      <input
        value={draft}
        onChange={e => setDraft(e.target.value)}
        placeholder={placeholder}
        style={{
          flex: 1, padding: '7px 0', fontSize: 12, fontFamily: 'inherit',
          color: '#e5e5e5', backgroundColor: 'transparent',
          border: 'none', outline: 'none',
        }}
      />
      {draft && (
        <button
          onClick={() => { setDraft(''); onChange('') }}
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
        >
          <X size={12} style={{ color: '#666' }} />
        </button>
      )}
    </div>
  )
}
