import type { CSSProperties } from 'react'

// The shared inline-style objects the system-config panels are built from.
// Lifted verbatim out of the ConfigTab component body so extracted panels can
// use them without threading six style props through every contract. This tree
// is inline-styled by design — do not convert these to Tailwind.

export const sectionStyle: CSSProperties = {
  background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden',
}

export const sectionHeaderStyle: CSSProperties = {
  padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600,
  display: 'flex', alignItems: 'center', gap: 10,
}

export const sectionBodyStyle: CSSProperties = { padding: 20 }

export const labelStyle: CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }

export const inputStyle: CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
  fontSize: 14, outline: 'none',
}

export const checkStyle: CSSProperties = { marginRight: 8, accentColor: 'var(--highlight-color, #eab308)' }
