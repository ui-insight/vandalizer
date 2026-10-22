import { useState } from 'react'

/**
 * An extracted value as text a person reads.
 *
 * List fields arrive as arrays or as JSON array strings, and chat showed them
 * raw: Key Personnel Role read `["PI","Co-Investigator",…` (support ticket,
 * NIH R01 Extraction). Lists become comma-separated items; objects become
 * "key: value" pairs.
 */
export function formatExtractedValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if ((trimmed.startsWith('[') && trimmed.endsWith(']')) || (trimmed.startsWith('{') && trimmed.endsWith('}'))) {
      try {
        return formatExtractedValue(JSON.parse(trimmed) as unknown)
      } catch {
        return value
      }
    }
    return value
  }
  if (Array.isArray(value)) {
    return value.map(formatExtractedValue).filter((item) => item.trim() !== '').join(', ')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${formatExtractedValue(item)}`)
      .join('; ')
  }
  return String(value)
}

/** Characters shown before a long value collapses behind "Show more". */
export const COLLAPSED_VALUE_CHARS = 160

/**
 * A value that shows in full on request. Long values used to end in "..."
 * at 80 characters with no way to read the rest.
 */
export function ExpandableValue({ value }: { value: unknown }) {
  const [expanded, setExpanded] = useState(false)
  const text = formatExtractedValue(value)
  const long = text.length > COLLAPSED_VALUE_CHARS
  return (
    <span style={{ color: '#374151', overflowWrap: 'anywhere' }}>
      {long && !expanded ? `${text.slice(0, COLLAPSED_VALUE_CHARS).trimEnd()}…` : text}
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          style={{
            background: 'none', border: 'none', padding: '0 var(--workspace-space-4)', cursor: 'pointer',
            color: '#3b82f6', fontSize: 'var(--workspace-font-meta)',
          }}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </span>
  )
}
